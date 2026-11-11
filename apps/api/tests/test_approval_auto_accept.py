"""Opt-in auto accept keeps the ordinary approval checks and project scope."""
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.task import Task
from app.services import approval_auto_accept_service as auto
from app.services import approval_service
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _project(client: TestClient, suffix: str) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"auto-ws-{suffix}"}).json()
    project = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"auto-p-{suffix}"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/mode",
        json={"mode": "agentic", "confirmation_title": "P"},
    )
    return project["id"]


def _headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/local-session").json()["token"]
    return {"X-Planarus-Local-Token": token}


def _propose(session: Session, project_id: str, title: str) -> ApprovalRequest:
    return approval_service.create_proposal(
        session, project_id=project_id, action_type="task.create", patch={"title": title}
    )


def test_auto_accept_is_off_until_local_control_enables_it(client, session, engine, monkeypatch):
    monkeypatch.setattr(auto, "engine", engine)
    pid = _project(client, "off")
    path = f"/api/v1/approvals/auto-accept?project_id={pid}"
    assert client.get(path).json() == {"project_id": pid, "enabled": False}
    assert client.put(path, json={"enabled": True}).status_code == 401

    first = _propose(session, pid, "First")
    auto.sweep()
    session.expire_all()
    assert session.get(ApprovalRequest, first.id).status == "pending"

    assert client.put(path, json={"enabled": True}, headers=_headers(client)).json() == {
        "project_id": pid, "enabled": True,
    }
    # The switch lives in the DB, not in the Approval Queue component. The
    # background sweep processes the existing backlog and later proposals.
    auto.sweep()
    second = _propose(session, pid, "Second")
    auto.sweep()
    session.expire_all()
    assert [session.get(ApprovalRequest, ar.id).status for ar in (first, second)] == ["applied", "applied"]
    assert {task.title for task in session.exec(select(Task).where(Task.project_id == pid)).all()} == {"First", "Second"}
    assert client.get(path).json()["enabled"] is True

    events = session.exec(select(AuditEvent).where(AuditEvent.entity_id == first.id)).all()
    assert [(e.event_type, e.actor_type) for e in events] == [
        ("proposal_created", "system"),
        ("proposal_approved", "system"),
        ("proposal_applied", "system"),
    ]

    assert client.put(path, json={"enabled": False}, headers=_headers(client)).json()["enabled"] is False
    third = _propose(session, pid, "Third")
    auto.sweep()
    session.expire_all()
    assert session.get(ApprovalRequest, third.id).status == "pending"


def test_auto_accept_is_scoped_and_stale_proposals_do_not_apply(client, session, engine, monkeypatch):
    monkeypatch.setattr(auto, "engine", engine)
    on = _project(client, "on")
    off = _project(client, "other")
    headers = _headers(client)
    client.put(f"/api/v1/approvals/auto-accept?project_id={on}", json={"enabled": True}, headers=headers)
    selected = _propose(session, on, "Selected")
    other = _propose(session, off, "Other")
    auto.sweep()
    session.expire_all()
    assert session.get(ApprovalRequest, selected.id).status == "applied"
    assert session.get(ApprovalRequest, other.id).status == "pending"

    task = session.exec(select(Task).where(Task.project_id == on)).one()
    update = approval_service.create_proposal(
        session, project_id=on, action_type="task.update",
        target_entity_id=task.id, patch={"title": "Overwrite"},
    )
    task.title = "Human edit"
    session.add(task)
    session.commit()
    auto.sweep()
    session.expire_all()
    assert session.get(ApprovalRequest, update.id).status == "invalidated"
    assert session.get(Task, task.id).title == "Human edit"


def test_normal_project_cannot_enable_auto_accept(client, session, engine, monkeypatch):
    monkeypatch.setattr(auto, "engine", engine)
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "auto-normal-ws"}).json()
    normal = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "Normal", "slug": "auto-normal"},
    ).json()
    path = f"/api/v1/approvals/auto-accept?project_id={normal['id']}"
    assert client.put(path, json={"enabled": True}, headers=_headers(client)).status_code == 403
