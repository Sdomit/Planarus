"""Phase 7C1: external proposal routes create pending proposals only."""
from types import SimpleNamespace

import pytest
from app.core.utils import new_id, now_utc
from app.mcp.tools.propose import REVIEW_HINT
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.task import Task
from app.services import approval_service
from sqlmodel import func, select

from tests.external_util import auth, issue_key, seed

T_CREATE = "/api/external/v1/proposals/task"
D_CREATE = "/api/external/v1/proposals/decision"
SECRET_VALUE = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENGbPxRfiCYEXAMPLEKEY"


@pytest.fixture
def env(client, external_api, session):
    ws, proj = seed(client, "prop")
    cm, raw = issue_key(client, ws, [proj], can_read=False, can_propose=True)
    return SimpleNamespace(ws=ws, proj=proj, key=raw, key_id=cm["key_id"], session=session)


def _count(session, model) -> int:
    return int(session.exec(select(func.count()).select_from(model)).one())


def test_task_create_proposal_is_pending_only(env, client):
    before = _count(env.session, Task)
    res = client.post(T_CREATE, headers=auth(env.key), json={"project_id": env.proj, "title": "Do it"})
    assert res.status_code == 202
    body = res.json()
    assert set(body) == {"approval_id", "status", "action_type", "expires_at", "review_hint"}
    assert body["status"] == "pending"
    assert body["action_type"] == "task.create"
    assert body["review_hint"] == REVIEW_HINT
    # Canonical state is untouched.
    assert _count(env.session, Task) == before
    ar = env.session.get(ApprovalRequest, body["approval_id"])
    assert ar.status == "pending"
    assert ar.origin == "api"
    assert ar.actor_ref == f"api:{env.key_id}"


def test_decision_create_proposal(env, client):
    res = client.post(D_CREATE, headers=auth(env.key), json={
        "project_id": env.proj, "title": "Pick X", "decision": "use X"})
    assert res.status_code == 202
    assert res.json()["action_type"] == "decision.create"


def test_task_update_proposal_derives_ownership(env, client, session):
    now = now_utc()
    task = Task(id=new_id("tsk"), project_id=env.proj, title="t", status="backlog",
                sort_order=0, created_at=now, updated_at=now)
    session.add(task)
    session.commit()
    res = client.post(f"/api/external/v1/proposals/task/{task.id}", headers=auth(env.key),
                      json={"status": "in_progress"})
    assert res.status_code == 202
    assert res.json()["action_type"] == "task.update"


def test_task_update_out_of_scope_returns_404(env, client, session):
    # A task in another (out-of-scope) project.
    _, other = seed(client, "prop2")
    now = now_utc()
    task = Task(id=new_id("tsk"), project_id=other, title="t", status="backlog",
                sort_order=0, created_at=now, updated_at=now)
    session.add(task)
    session.commit()
    res = client.post(f"/api/external/v1/proposals/task/{task.id}", headers=auth(env.key),
                      json={"status": "in_progress"})
    assert res.status_code == 404


def test_idempotent_duplicate_returns_same_proposal(env, client):
    body = {"project_id": env.proj, "title": "same task"}
    a = client.post(T_CREATE, headers=auth(env.key), json=body).json()["approval_id"]
    b = client.post(T_CREATE, headers=auth(env.key), json=body).json()["approval_id"]
    assert a == b


def test_fresh_proposal_after_terminal_predecessor(env, client, session):
    body = {"project_id": env.proj, "title": "again"}
    first = client.post(T_CREATE, headers=auth(env.key), json=body).json()["approval_id"]
    # Reject → terminal → frees the idempotency key.
    approval_service.reject(session, first)
    second = client.post(T_CREATE, headers=auth(env.key), json=body).json()["approval_id"]
    assert second != first


def test_secret_value_rejected_with_no_row_or_audit(env, client, session):
    ar_before = _count(session, ApprovalRequest)
    audit_before = _count(session, AuditEvent)
    res = client.post(T_CREATE, headers=auth(env.key), json={
        "project_id": env.proj, "title": "t", "description": SECRET_VALUE})
    assert res.status_code == 422
    assert res.json()["type"].endswith("/secret_detected")
    # The offending value never appears in the response.
    assert SECRET_VALUE not in res.text
    assert _count(session, ApprovalRequest) == ar_before
    assert _count(session, AuditEvent) == audit_before


def test_read_only_key_cannot_propose(client, external_api):
    ws, proj = seed(client, "ronly2")
    _, raw = issue_key(client, ws, [proj], can_read=True, can_propose=False)
    res = client.post(T_CREATE, headers=auth(raw), json={"project_id": proj, "title": "x"})
    assert res.status_code == 403
    assert res.json()["type"].endswith("/forbidden")


def test_forbidden_field_rejected(env, client):
    res = client.post(T_CREATE, headers=auth(env.key), json={
        "project_id": env.proj, "title": "t", "bogus": "x"})
    assert res.status_code == 422


@pytest.mark.parametrize("verb", ["approve", "apply", "reject", "invalidate"])
def test_no_external_mutation_routes_exist(env, client, verb):
    # Create a real pending approval, then confirm no external route can act on it.
    ar = approval_service.create_proposal(
        env.session, project_id=env.proj, action_type="task.create", patch={"title": "x"})
    res = client.post(f"/api/external/v1/approvals/{ar.id}/{verb}", headers=auth(env.key))
    assert res.status_code in (404, 405)
    # And the proposal is still pending (nothing acted on it).
    env.session.refresh(ar)
    assert ar.status == "pending"
