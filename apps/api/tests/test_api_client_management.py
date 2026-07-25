"""Phase 7C1: local-human-only ApiClient management endpoints."""
from datetime import datetime

from app.models.audit_event import AuditEvent
from sqlmodel import select

from tests.external_util import auth, create_api_client, issue_key, local_hdr, seed

CLIENTS = "/api/v1/api-clients"


# --- local control protection ------------------------------------------------


def test_management_requires_local_token(client):
    ws, proj = seed(client, "mgmt")
    # No token → 401 on every management route.
    assert client.get(CLIENTS).status_code == 401
    assert client.post(CLIENTS, json={"label": "l", "workspace_id": ws,
                                       "project_ids": [proj], "can_read": True}).status_code == 401
    assert client.post(f"{CLIENTS}/x/revoke").status_code == 401


def test_management_rejects_foreign_origin(client):
    res = client.get(CLIENTS, headers={"Origin": "http://evil.example"})
    assert res.status_code == 403


def test_management_does_not_accept_api_key_as_auth(client, external_api):
    ws, proj = seed(client, "mgmt2")
    _, raw = issue_key(client, ws, [proj], can_read=True)
    # A valid external API key is NOT valid management auth.
    res = client.get(CLIENTS, headers={"Authorization": f"Bearer {raw}"})
    assert res.status_code == 401


# --- one-time key + secret hygiene ------------------------------------------


def test_create_returns_key_once_then_never(client):
    ws, proj = seed(client, "once")
    res = create_api_client(client, ws, [proj], can_read=True)
    assert res.status_code == 201
    data = res.json()
    raw = data["api_key"]
    assert raw.startswith("agbk_")
    assert "warning" in data
    assert "secret_hash" not in str(data)
    # List never includes the raw key or hash.
    listed = client.get(CLIENTS, headers=local_hdr(client)).json()
    assert raw not in str(listed)
    for item in listed:
        assert "secret_hash" not in item and "api_key" not in item


def test_raw_key_absent_from_audit(client, session):
    ws, proj = seed(client, "audit")
    raw = create_api_client(client, ws, [proj], can_read=True).json()["api_key"]
    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "api_client_created")
    ).all()
    assert events
    for ev in events:
        assert raw not in (ev.payload_json or "")


# --- creation validation -----------------------------------------------------


def test_at_least_one_permission_required(client):
    ws, proj = seed(client, "perm")
    res = create_api_client(client, ws, [proj], can_read=False, can_propose=False)
    assert res.status_code == 422


def test_explicit_non_empty_project_list_required(client):
    ws, _ = seed(client, "empty")
    res = create_api_client(client, ws, [], can_read=True)
    assert res.status_code == 422


def test_project_count_cap_50(client):
    ws, _ = seed(client, "cap")
    res = create_api_client(client, ws, [f"p{i}" for i in range(51)], can_read=True)
    assert res.status_code == 422


def test_duplicate_project_ids_rejected(client):
    ws, proj = seed(client, "dup")
    res = create_api_client(client, ws, [proj, proj], can_read=True)
    assert res.status_code == 422


def test_cross_workspace_project_rejected(client):
    ws1, _ = seed(client, "wsa")
    _, proj2 = seed(client, "wsb")
    res = create_api_client(client, ws1, [proj2], can_read=True)
    assert res.status_code == 422


def test_default_expiry_is_90_days(client):
    ws, proj = seed(client, "exp")
    data = create_api_client(client, ws, [proj], can_read=True).json()["client"]
    created = datetime.fromisoformat(data["created_at"])
    expires = datetime.fromisoformat(data["expires_at"])
    days = (expires - created).total_seconds() / 86400
    assert 89.9 < days < 90.1


def test_expiry_out_of_range_rejected(client):
    ws, proj = seed(client, "exprange")
    res = create_api_client(client, ws, [proj], can_read=True, expires_in_days=400)
    assert res.status_code == 422
    res2 = create_api_client(client, ws, [proj], can_read=True, expires_in_days=0)
    assert res2.status_code == 422


def test_custom_expiry_within_range(client):
    ws, proj = seed(client, "exp1")
    data = create_api_client(client, ws, [proj], can_read=True, expires_in_days=1).json()["client"]
    created = datetime.fromisoformat(data["created_at"])
    expires = datetime.fromisoformat(data["expires_at"])
    assert 0.9 < (expires - created).total_seconds() / 86400 < 1.1


# --- revoke ------------------------------------------------------------------


def test_revoke_is_one_way_and_blocks_next_request(client, external_api):
    ws, proj = seed(client, "rev")
    cm, raw = issue_key(client, ws, [proj], can_read=True)
    # Works first.
    assert client.get("/api/external/v1/projects", headers=auth(raw)).status_code == 200
    rev = client.post(f"{CLIENTS}/{cm['id']}/revoke", headers=local_hdr(client))
    assert rev.status_code == 200
    assert rev.json()["revoked_at"] is not None
    assert "api_key" not in str(rev.json())
    # Next external request is rejected immediately.
    assert client.get("/api/external/v1/projects", headers=auth(raw)).status_code == 401


def test_revoke_unknown_returns_404(client):
    res = client.post(f"{CLIENTS}/nope/revoke", headers=local_hdr(client))
    assert res.status_code == 404


def test_no_reenable_or_delete_endpoint(client):
    ws, proj = seed(client, "noenable")
    cm, _ = issue_key(client, ws, [proj], can_read=True)
    # There is no enable/delete route.
    assert client.post(f"{CLIENTS}/{cm['id']}/enable", headers=local_hdr(client)).status_code in (404, 405)
    assert client.delete(f"{CLIENTS}/{cm['id']}", headers=local_hdr(client)).status_code in (404, 405)
