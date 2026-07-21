"""Phase 13c: doc.update approval path (AI-proposed canvas edits).

Mirrors the Phase 7A guarantees for the new ``doc`` target: propose through the
internal service seam, approve/apply through the HTTP routes + local token, with
the same fail-closed behaviour — stale-target invalidation, secret rejection,
per-action size cap, and content_json JSON validation. Nothing canonical mutates
until a local human approves and applies the exact proposal.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.exceptions import PolicyError, SecretDetectedError
from app.core.utils import now_utc
from app.models.approval_request import ApprovalRequest
from app.models.doc import Doc
from app.services import approval_service


def _seed(client: TestClient, suffix: str = "docapr") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def _hdr(client: TestClient) -> dict:
    token = client.get("/api/v1/local-session").json()["token"]
    return {"X-Planarus-Local-Token": token}


def _canvas(client: TestClient, pid: str) -> dict:
    return client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Board", "doc_type": "canvas", "editor_format": "excalidraw"},
    ).json()


def _scene(n: int = 1, text: str = "") -> str:
    els = [{"id": f"e{i}", "type": "rectangle", "version": i + 1} for i in range(n)]
    if text:
        els.append({"id": "t", "type": "text", "version": 1, "text": text})
    return json.dumps(
        {"type": "excalidraw", "version": 2, "elements": els, "appState": {}, "files": {}}
    )


def _propose(session: Session, pid: str, doc_id: str, content: str, cache: str = "") -> ApprovalRequest:
    return approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="doc.update",
        patch={"content_json": content, "markdown_cache": cache},
        target_entity_id=doc_id,
    )


def test_doc_update_propose_is_pending_only(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    doc = _canvas(client, pid)
    new = _scene(3)
    ar = _propose(session, pid, doc["id"], new)
    assert ar.status == "pending"
    assert ar.action_type == "doc.update" and ar.target_entity_type == "doc"
    assert ar.risk_level == "medium"
    # canonical scene is untouched until a human approves + applies
    session.expire_all()
    assert session.get(Doc, doc["id"]).content_json != new


def test_doc_update_approve_apply_replaces_scene(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    doc = _canvas(client, pid)
    new = _scene(3)
    ar = _propose(session, pid, doc["id"], new)
    assert client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client)).status_code == 200
    rp = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert rp.status_code == 200 and rp.json()["status"] == "applied"
    session.expire_all()
    d = session.get(Doc, doc["id"])
    assert d.content_json == new
    assert d.version == doc["version"] + 1  # bumped so an open editor reloads


def test_doc_update_reject_leaves_doc_unchanged(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    doc = _canvas(client, pid)
    before = session.get(Doc, doc["id"]).content_json
    ar = _propose(session, pid, doc["id"], _scene(9))
    assert client.post(f"/api/v1/approvals/{ar.id}/reject", headers=_hdr(client)).status_code == 200
    session.expire_all()
    assert session.get(Doc, doc["id"]).content_json == before


def test_doc_update_stale_target_fails_closed(client: TestClient, session: Session) -> None:
    """A human edit between approve and apply must invalidate — never overwrite."""
    pid = _seed(client)
    doc = _canvas(client, pid)
    ar = _propose(session, pid, doc["id"], _scene(3))
    assert client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client)).status_code == 200
    # human edits the canvas after approval, before apply
    human = _scene(7)
    d = session.get(Doc, doc["id"])
    d.content_json = human
    d.version += 1
    d.updated_at = now_utc()
    session.add(d)
    session.commit()

    rp = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert rp.status_code == 409  # stale — fails closed
    session.expire_all()
    assert session.get(Doc, doc["id"]).content_json == human  # AI content NOT applied
    ar2 = session.get(ApprovalRequest, ar.id)
    session.refresh(ar2)
    assert ar2.status == "invalidated"


def test_doc_update_secret_in_scene_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    doc = _canvas(client, pid)
    scene = _scene(1, text="deploy key AKIAIOSFODNN7EXAMPLE")
    with pytest.raises(SecretDetectedError):
        _propose(session, pid, doc["id"], scene)
    # nothing was written
    assert session.exec(select(ApprovalRequest).where(ApprovalRequest.project_id == pid)).all() == []


def test_doc_update_oversize_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    doc = _canvas(client, pid)
    huge = json.dumps({"type": "excalidraw", "elements": [], "blob": "a" * (3 * 1024 * 1024 + 1000)})
    with pytest.raises(PolicyError):
        _propose(session, pid, doc["id"], huge)


def test_doc_update_invalid_json_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    doc = _canvas(client, pid)
    with pytest.raises(PolicyError):
        _propose(session, pid, doc["id"], "this is not json")


def test_doc_update_target_must_exist(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(LookupError):
        _propose(session, pid, "doc_does_not_exist", _scene(1))
