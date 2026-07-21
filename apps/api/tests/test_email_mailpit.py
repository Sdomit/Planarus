"""Real-Mailpit integration (Phase 9). Skipped unless Mailpit is running locally.

Start Mailpit (https://mailpit.axllent.org) with its defaults — SMTP on
127.0.0.1:1025, HTTP UI/API on 127.0.0.1:8025 — and this test sends a real
reminder through the full endpoint stack, then asserts via Mailpit's REST API.
"""
import json
import socket
import urllib.request
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

_PAST = "2000-01-01T00:00:00+00:00"


def _mailpit_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 1025), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _mailpit_up(), reason="Mailpit not running on 127.0.0.1:1025"
)


def test_reminder_reaches_mailpit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", 1025)

    marker = uuid.uuid4().hex[:12]
    ws = client.post(
        "/api/v1/workspaces", json={"name": "WS", "slug": f"ws-mp-{marker}"}
    ).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": f"Mailpit {marker}", "slug": f"p-mp-{marker}"},
    ).json()
    pid = proj["id"]
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Overdue thing", "due_at": _PAST})

    token = client.get("/api/v1/local-session").json()["token"]
    hdr = {"X-Planarus-Local-Token": token}
    client.post(
        f"/api/v1/projects/{pid}/notification-rules",
        json={"to_email": f"inbox-{marker}@example.com"},
        headers=hdr,
    )
    res = client.post(f"/api/v1/projects/{pid}/reminders/send", headers=hdr)
    assert res.status_code == 200
    assert res.json()["sent"] == 1

    with urllib.request.urlopen(
        f"http://127.0.0.1:8025/api/v1/search?query={marker}", timeout=5
    ) as resp:
        found = json.loads(resp.read())
    assert found["messages_count"] >= 1
