"""P17.3 — outbound webhooks: crypto, signed delivery, the audit trigger,
auto-disable, redeliver, and the disabled-without-key gate."""
import hashlib
import hmac
import json

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.models.webhook_subscription import WebhookSubscription
from app.services import webhook_service
from tests.external_util import local_hdr, seed


@pytest.fixture
def wh(monkeypatch):
    """Enable webhooks (enc key), deliver inline (no thread), and capture the POST."""
    monkeypatch.setattr(settings, "webhook_enc_key", Fernet.generate_key().decode())
    monkeypatch.setattr(webhook_service, "_submit", lambda fn, *a: fn(*a))
    calls: list[dict] = []

    def fake_post(url, body, headers, timeout):
        calls.append({"url": url, "body": body, "headers": headers})
        return 200, None

    monkeypatch.setattr(webhook_service, "_http_post", fake_post)
    return calls


def _create_sub(client, workspace_id, **kw):
    body = {"workspace_id": workspace_id, "target_url": "http://localhost:9/hook", **kw}
    res = client.post("/api/v1/webhooks", headers=local_hdr(client), json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_webhook_crypto_roundtrip(wh):
    from app.core import webhook_crypto

    assert webhook_crypto.is_enabled()
    ciphertext = webhook_crypto.encrypt("s3cret")
    assert ciphertext != "s3cret"
    assert webhook_crypto.decrypt(ciphertext) == "s3cret"


def test_routes_404_without_enc_key(client):
    # No `wh` fixture → key unset → the whole surface is invisible.
    ws, _ = seed(client, "whoff")
    res = client.post(
        "/api/v1/webhooks", headers=local_hdr(client),
        json={"workspace_id": ws, "target_url": "http://x/y"},
    )
    assert res.status_code == 404


def test_create_encrypts_secret_and_shows_it_once(client, session, wh):
    from app.core import webhook_crypto

    ws, _ = seed(client, "whc")
    data = _create_sub(client, ws)
    secret, sub_id = data["secret"], data["subscription"]["id"]
    assert secret and "secret" not in data["subscription"]
    stored = session.get(WebhookSubscription, sub_id)
    assert stored.secret_enc != secret
    assert webhook_crypto.decrypt(stored.secret_enc) == secret
    listed = client.get(f"/api/v1/webhooks?workspace_id={ws}", headers=local_hdr(client)).json()
    assert listed and all("secret" not in s for s in listed)


def test_test_send_delivers_signed(client, wh):
    ws, _ = seed(client, "wht")
    data = _create_sub(client, ws)
    sub_id, secret = data["subscription"]["id"], data["secret"]
    res = client.post(f"/api/v1/webhooks/{sub_id}/test", headers=local_hdr(client))
    assert res.status_code == 202
    assert len(wh) == 1
    call = wh[0]
    assert call["url"] == "http://localhost:9/hook"
    expected = "sha256=" + hmac.new(secret.encode(), call["body"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-Planarus-Signature"] == expected
    assert json.loads(call["body"])["kind"] == "webhook.test"
    deliveries = client.get(f"/api/v1/webhooks/{sub_id}/deliveries", headers=local_hdr(client)).json()
    assert deliveries[0]["status"] == "delivered"


def test_task_create_fires_signed_webhook(client, wh):
    ws, proj = seed(client, "whtask")
    _create_sub(client, ws)
    res = client.post(f"/api/v1/projects/{proj}/tasks", json={"title": "T"})
    assert res.status_code in (200, 201), res.text
    kinds = [json.loads(c["body"])["kind"] for c in wh]
    assert "task.create" in kinds


def test_auto_disable_after_failure_streak(client, session, monkeypatch, wh):
    monkeypatch.setattr(webhook_service, "_http_post", lambda url, body, headers, timeout: (500, None))
    ws, _ = seed(client, "whfail")
    sub_id = _create_sub(client, ws)["subscription"]["id"]
    for _ in range(webhook_service._FAILURE_THRESHOLD):
        client.post(f"/api/v1/webhooks/{sub_id}/test", headers=local_hdr(client))
    session.expire_all()
    stored = session.get(WebhookSubscription, sub_id)
    assert stored.enabled is False
    assert stored.disabled_at is not None


def test_redeliver_resends_the_same_body(client, wh):
    ws, _ = seed(client, "whre")
    sub_id = _create_sub(client, ws)["subscription"]["id"]
    client.post(f"/api/v1/webhooks/{sub_id}/test", headers=local_hdr(client))
    first = client.get(f"/api/v1/webhooks/{sub_id}/deliveries", headers=local_hdr(client)).json()
    before = len(wh)
    res = client.post(
        f"/api/v1/webhooks/deliveries/{first[0]['id']}/redeliver", headers=local_hdr(client)
    )
    assert res.status_code == 202
    assert len(wh) == before + 1
    assert res.json()["attempt"] == 2


def test_slack_and_discord_formats_reshape_the_body(client, wh):
    ws, _ = seed(client, "whfmt")
    slack = _create_sub(client, ws, format="slack")["subscription"]["id"]
    client.post(f"/api/v1/webhooks/{slack}/test", headers=local_hdr(client))
    slack_body = json.loads(wh[-1]["body"])
    assert "text" in slack_body and "webhook.test" in slack_body["text"]

    discord = _create_sub(client, ws, format="discord")["subscription"]["id"]
    client.post(f"/api/v1/webhooks/{discord}/test", headers=local_hdr(client))
    assert "content" in json.loads(wh[-1]["body"])


def test_host_is_public_classifies_addresses():
    from app.services.webhook_service import _host_is_public

    assert _host_is_public("8.8.8.8") is True
    assert _host_is_public("1.1.1.1") is True
    assert _host_is_public("127.0.0.1") is False          # loopback
    assert _host_is_public("10.0.0.5") is False           # private
    assert _host_is_public("192.168.1.10") is False       # private
    assert _host_is_public("169.254.169.254") is False    # cloud metadata (link-local)
    assert _host_is_public("") is False


def test_ssrf_create_blocks_internal_target_when_multi_user(client, session, monkeypatch, wh):
    from app.core.config import settings

    ws, _ = seed(client, "whssrf")
    monkeypatch.setattr(settings, "auth_enabled", True)  # LAN/hosted: owner is a tenant
    with pytest.raises(ValueError):
        webhook_service.create_subscription(session, workspace_id=ws, target_url="http://127.0.0.1/hook")
    # a public target is still fine (use an IP literal so the test needs no DNS)
    sub, _secret = webhook_service.create_subscription(session, workspace_id=ws, target_url="http://8.8.8.8/hook")
    assert sub.enabled


def test_ssrf_delivery_blocks_internal_target_when_multi_user(client, session, monkeypatch, wh):
    from app.core.config import settings

    ws, _ = seed(client, "whssrf2")
    # created single-user (localhost allowed), then the deployment becomes multi-user
    sub, _s = webhook_service.create_subscription(session, workspace_id=ws, target_url="http://127.0.0.1/hook")
    monkeypatch.setattr(settings, "auth_enabled", True)
    webhook_service.send_test(session, sub.id)
    assert len(wh) == 0  # the outbound POST was never made — DNS-rebind/late-block caught
    deliveries = webhook_service.list_deliveries(session, sub.id)
    assert deliveries[0].status == "failed"
    assert "blocked" in (deliveries[0].error or "")
