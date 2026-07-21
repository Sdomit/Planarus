"""Phase 9 email reminders: rules CRUD, guarded manual send, cap, fail-closed scan.

Rule create/update and the send trigger are all local-control-token gated (they
configure or fire an outbound side effect). The SMTP client is faked at the
email_service seam — no socket is opened. The real-Mailpit integration lives in
test_email_mailpit.py (skipped when Mailpit is not running).
"""
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models.audit_event import AuditEvent
from app.services import email_service

_PAST = "2000-01-01T00:00:00+00:00"


def _seed(client: TestClient, suffix: str = "eml") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": f"Mail {suffix}", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def _hdr(client: TestClient) -> dict:
    token = client.get("/api/v1/local-session").json()["token"]
    return {"X-Planarus-Local-Token": token}


def _post_rule(client: TestClient, pid: str, **payload):
    return client.post(
        f"/api/v1/projects/{pid}/notification-rules",
        json={"to_email": "me@example.com", **payload},
        headers=_hdr(client),
    )


def _patch_rule(client: TestClient, rule_id: str, **payload):
    return client.patch(
        f"/api/v1/notification-rules/{rule_id}", json=payload, headers=_hdr(client)
    )


class _FakeSMTP:
    sent: list[EmailMessage] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host, self.port = host, port

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def send_message(self, msg: EmailMessage) -> None:
        if _FakeSMTP.fail:
            raise ConnectionRefusedError("boom")
        _FakeSMTP.sent.append(msg)


@pytest.fixture(name="email_on")
def email_on_fixture(monkeypatch):
    """Enable email + fake the SMTP client. Restored automatically."""
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent = []
    _FakeSMTP.fail = False
    yield
    _FakeSMTP.sent = []
    _FakeSMTP.fail = False


# --- rules CRUD ----------------------------------------------------------------


def test_rule_create_requires_local_token(client: TestClient) -> None:
    pid = _seed(client, suffix="eml0")
    res = client.post(
        f"/api/v1/projects/{pid}/notification-rules",
        json={"to_email": "me@example.com"},
    )
    assert res.status_code == 401


def test_rule_create_defaults(client: TestClient) -> None:
    pid = _seed(client)
    res = _post_rule(client, pid)
    assert res.status_code == 201
    data = res.json()
    assert data["id"].startswith("nrl_")
    assert data["channel"] == "email"
    assert data["trigger_type"] == "due_soon"
    assert data["enabled"] is True
    assert data["threshold_hours"] == 48


def test_rule_validation(client: TestClient) -> None:
    pid = _seed(client, suffix="eml2")
    assert _post_rule(client, pid, to_email="not-an-email").status_code == 422
    assert _post_rule(client, pid, channel="fax").status_code == 422
    # in_app/desktop are canonical channel values but inert today → rejected.
    assert _post_rule(client, pid, channel="in_app").status_code == 422
    assert _post_rule(client, pid, trigger_type="hourly").status_code == 422
    assert _post_rule(client, pid, threshold_hours=0).status_code == 422
    assert _post_rule(client, "proj_nope").status_code == 404


def test_rule_update(client: TestClient) -> None:
    pid = _seed(client, suffix="eml3")
    rule = _post_rule(client, pid).json()
    assert (
        client.patch(f"/api/v1/notification-rules/{rule['id']}", json={"enabled": False}).status_code
        == 401
    )  # no token
    res = _patch_rule(
        client, rule["id"], enabled=False, to_email="you@example.com", threshold_hours=12
    )
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["to_email"] == "you@example.com"
    assert data["threshold_hours"] == 12
    assert _patch_rule(client, "nrl_nope").status_code == 404


# --- manual send guards ----------------------------------------------------------


def test_send_requires_local_token(client: TestClient) -> None:
    pid = _seed(client, suffix="eml4")
    assert client.post(f"/api/v1/projects/{pid}/reminders/send").status_code == 401


def test_send_disabled_by_default(client: TestClient) -> None:
    pid = _seed(client, suffix="eml5")
    res = client.post(f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client))
    assert res.status_code == 409
    assert "disabled" in res.json()["detail"]


def test_send_refuses_non_loopback_smtp(client: TestClient, monkeypatch) -> None:
    pid = _seed(client, suffix="eml6")
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    res = client.post(f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client))
    assert res.status_code == 409
    assert "loopback" in res.json()["detail"]


def test_send_project_not_found(client: TestClient, email_on) -> None:
    res = client.post("/api/v1/projects/proj_nope/reminders/send", headers=_hdr(client))
    assert res.status_code == 404


# --- sending -------------------------------------------------------------------


def test_send_due_soon_reminder(client: TestClient, session: Session, email_on) -> None:
    pid = _seed(client, suffix="eml7")
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Late", "due_at": _PAST})
    _post_rule(client, pid)
    res = client.post(f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client))
    assert res.status_code == 200
    data = res.json()
    assert data["sent"] == 1 and data["failed"] == 0 and data["skipped"] == 0
    assert data["outcomes"][0]["email_log_id"].startswith("eml_")

    assert len(_FakeSMTP.sent) == 1
    msg = _FakeSMTP.sent[0]
    assert msg["To"] == "me@example.com"
    assert "Mail eml7" in msg["Subject"]
    assert "Late" in msg.get_content()

    log = client.get(f"/api/v1/projects/{pid}/email-log").json()
    assert len(log) == 1
    assert log[0]["status"] == "sent"
    assert log[0]["to_email"] == "me@example.com"

    audit = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "email_send")
    ).all()
    assert len(audit) == 1


def test_send_due_soon_nothing_due_skips(client: TestClient, email_on) -> None:
    pid = _seed(client, suffix="eml8")
    _post_rule(client, pid)
    data = client.post(
        f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client)
    ).json()
    assert data["skipped"] == 1 and data["sent"] == 0
    assert data["outcomes"][0]["reason"] == "nothing due"
    assert _FakeSMTP.sent == []
    assert client.get(f"/api/v1/projects/{pid}/email-log").json() == []


def test_due_soon_ignores_unparseable_and_future_offsets(
    client: TestClient, email_on
) -> None:
    """due_at is parsed, not string-compared: non-UTC offsets bucket correctly
    and unparseable values are excluded rather than misclassified."""
    pid = _seed(client, suffix="eml8b")
    # Overdue in UTC even though the string sorts after now_utc() lexically.
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Offset overdue", "due_at": "2000-01-01T09:00:00+09:00"},
    )
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Garbage date", "due_at": "next Friday"},
    )
    _post_rule(client, pid)
    client.post(f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client))
    assert len(_FakeSMTP.sent) == 1
    body = _FakeSMTP.sent[0].get_content()
    assert "Offset overdue" in body
    assert "Garbage date" not in body


def test_send_daily_digest_always_sends(client: TestClient, email_on) -> None:
    pid = _seed(client, suffix="eml9")
    _post_rule(client, pid, trigger_type="daily_digest")
    data = client.post(
        f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client)
    ).json()
    assert data["sent"] == 1
    assert "daily digest" in _FakeSMTP.sent[0]["Subject"]


def test_send_disabled_rule_ignored(client: TestClient, email_on) -> None:
    pid = _seed(client, suffix="eml10")
    rule = _post_rule(client, pid, trigger_type="daily_digest").json()
    _patch_rule(client, rule["id"], enabled=False)
    data = client.post(
        f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client)
    ).json()
    assert data["outcomes"] == []
    assert _FakeSMTP.sent == []


def test_send_fail_closed_on_secretlike_content(client: TestClient, email_on) -> None:
    pid = _seed(client, suffix="eml11")
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "rotate password: hunter2secret", "due_at": _PAST},
    )
    _post_rule(client, pid)
    data = client.post(
        f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client)
    ).json()
    assert data["failed"] == 1 and data["sent"] == 0
    assert "secret" in data["outcomes"][0]["reason"]
    assert _FakeSMTP.sent == []  # nothing left the process
    log = client.get(f"/api/v1/projects/{pid}/email-log").json()
    assert log[0]["status"] == "failed"


def test_send_daily_cap(client: TestClient, email_on, monkeypatch) -> None:
    pid = _seed(client, suffix="eml12")
    monkeypatch.setattr(email_service, "EMAIL_DAILY_CAP", 1)
    for addr in ("a@example.com", "b@example.com"):
        _post_rule(client, pid, to_email=addr, trigger_type="daily_digest")
    data = client.post(
        f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client)
    ).json()
    assert data["sent"] == 1 and data["skipped"] == 1
    assert any(o["reason"] == "daily email cap reached" for o in data["outcomes"])
    assert len(_FakeSMTP.sent) == 1


def test_send_smtp_failure_recorded(client: TestClient, email_on) -> None:
    pid = _seed(client, suffix="eml13")
    _post_rule(client, pid, trigger_type="daily_digest")
    _FakeSMTP.fail = True
    data = client.post(
        f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client)
    ).json()
    assert data["failed"] == 1
    log = client.get(f"/api/v1/projects/{pid}/email-log").json()
    assert log[0]["status"] == "failed"
    assert "ConnectionRefusedError" in log[0]["error"]


def test_email_log_newest_first_and_limit(client: TestClient, email_on) -> None:
    pid = _seed(client, suffix="eml14")
    _post_rule(client, pid, trigger_type="daily_digest")
    for _ in range(3):
        client.post(f"/api/v1/projects/{pid}/reminders/send", headers=_hdr(client))
    log = client.get(f"/api/v1/projects/{pid}/email-log?limit=2").json()
    assert len(log) == 2
    ats = [row["sent_at"] for row in log]
    assert ats == sorted(ats, reverse=True)
