import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.mcp import errors
from app.mcp.registry import PROPOSE_TOOLS
from app.mcp.tools import propose
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.decision import Decision
from app.models.task import Task
from app.schemas.task import TaskCreate
from app.services import approval_service, task_service
from tests.mcp_util import propose_cap, read_cap, seed


def _approvals(session, pid):
    return list(session.exec(select(ApprovalRequest).where(ApprovalRequest.project_id == pid)).all())


def test_create_task_proposal_pending_only(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp1")
    cap = propose_cap(ws, pid)
    res = propose.create_task_proposal(
        session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="from mcp", status="ready")
    )
    assert res.metadata["status"] == "pending"
    assert set(res.metadata) == {"approval_id", "status", "action_type", "expires_at", "review_hint"}
    assert res.metadata["review_hint"].startswith("Pending human review in AgentBoard Approval Queue")
    ars = _approvals(session, pid)
    assert len(ars) == 1
    assert ars[0].origin == "mcp" and ars[0].actor_ref == "mcp:test"
    # canonical state unchanged
    assert session.exec(select(Task).where(Task.project_id == pid)).all() == []


def test_create_decision_proposal_pending_only(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp2")
    cap = propose_cap(ws, pid)
    res = propose.create_decision_proposal(
        session, cap, propose.CreateDecisionProposalArgs(project_id=pid, title="D", decision="Do X")
    )
    assert res.metadata["action_type"] == "decision.create"
    assert len(_approvals(session, pid)) == 1
    assert session.exec(select(Decision).where(Decision.project_id == pid)).all() == []


def test_update_task_derives_project_and_stays_pending(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp3")
    task = task_service.create_task(session, pid, TaskCreate(title="orig", status="backlog"))
    cap = propose_cap(ws, pid)
    res = propose.update_task_proposal(
        session, cap, propose.UpdateTaskProposalArgs(task_id=task.id, status="in_progress")
    )
    assert res.metadata["action_type"] == "task.update"
    ar = _approvals(session, pid)[0]
    assert ar.target_entity_id == task.id and ar.project_id == pid
    # canonical task unchanged
    assert session.get(Task, task.id).status == "backlog"


def test_read_tier_cannot_propose(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp4")
    cap = read_cap(ws, pid)
    with pytest.raises(errors.MCPToolError) as e:
        propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="x"))
    assert e.value.code == errors.CODE_FORBIDDEN
    assert _approvals(session, pid) == []


def test_cross_project_create_forbidden(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp5")
    _, pid2 = seed(client, "pp6")
    cap = propose_cap(ws, pid)
    with pytest.raises(errors.MCPToolError) as e:
        propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid2, title="x"))
    assert e.value.code == errors.CODE_FORBIDDEN


def test_update_out_of_scope_task_not_found(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp7")
    _, pid2 = seed(client, "pp8")
    task2 = task_service.create_task(session, pid2, TaskCreate(title="b"))
    cap = propose_cap(ws, pid)
    with pytest.raises(errors.MCPToolError) as e:
        propose.update_task_proposal(session, cap, propose.UpdateTaskProposalArgs(task_id=task2.id, status="done"))
    assert e.value.code == errors.CODE_NOT_FOUND


def test_unknown_field_rejected_by_schema():
    spec = PROPOSE_TOOLS["create_task_proposal"]
    with pytest.raises(errors.MCPToolError) as e:
        spec.validate_args({"project_id": "p", "title": "t", "bogus": "x"})
    assert e.value.code == errors.CODE_INVALID


def test_update_rejects_project_id_field():
    # project_id is not an accepted field on update (ownership derived from task).
    spec = PROPOSE_TOOLS["update_task_proposal"]
    with pytest.raises(errors.MCPToolError):
        spec.validate_args({"task_id": "t", "project_id": "p"})


def test_secret_proposal_rejected_no_row_no_audit(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp9")
    cap = propose_cap(ws, pid)
    with pytest.raises(errors.MCPToolError) as e:
        propose.create_task_proposal(
            session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="key AKIAIOSFODNN7EXAMPLE")
        )
    assert e.value.code == errors.CODE_SECRET
    assert "AKIAIOSFODNN7EXAMPLE" not in str(e.value.message)
    assert _approvals(session, pid) == []
    audit = session.exec(
        select(AuditEvent).where(AuditEvent.entity_type == "approval_request")
    ).all()
    assert list(audit) == []


def test_idempotency_dedupe(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp10")
    cap = propose_cap(ws, pid)
    a = propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="dup"))
    b = propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="dup"))
    assert a.metadata["approval_id"] == b.metadata["approval_id"]
    assert len(_approvals(session, pid)) == 1


def test_idempotency_fresh_after_terminal(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pp11")
    cap = propose_cap(ws, pid)
    a = propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="dup"))
    approval_service.reject(session, a.metadata["approval_id"])
    b = propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="dup"))
    assert a.metadata["approval_id"] != b.metadata["approval_id"]
    assert len(_approvals(session, pid)) == 2


def test_failed_proposal_dedupes_no_double_create(
    client: TestClient, session: Session, monkeypatch
) -> None:
    """A failed proposal stays in the active idempotency set, so an identical
    re-proposal dedupes to it instead of creating a second applicable row."""
    from app.core.exceptions import ApprovalApplyError

    ws, pid = seed(client, "pp13")
    cap = propose_cap(ws, pid)
    a = propose.create_task_proposal(
        session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="dup-fail")
    )
    apr_id = a.metadata["approval_id"]
    approval_service.approve(session, apr_id)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("disk")

    monkeypatch.setattr(approval_service.handlers, "apply_action", _boom)
    with pytest.raises(ApprovalApplyError):
        approval_service.apply(session, apr_id)
    assert session.get(ApprovalRequest, apr_id).status == "failed"
    monkeypatch.undo()

    b = propose.create_task_proposal(
        session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="dup-fail")
    )
    assert b.metadata["approval_id"] == apr_id  # deduped to the failed one
    assert len(_approvals(session, pid)) == 1


def test_proposal_then_human_apply_mutates(client: TestClient, session: Session) -> None:
    """End-to-end: MCP proposes (pending), local human approves+applies → canonical change."""
    ws, pid = seed(client, "pp12")
    cap = propose_cap(ws, pid)
    res = propose.create_task_proposal(
        session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="via approval", status="ready")
    )
    apr_id = res.metadata["approval_id"]
    assert session.exec(select(Task).where(Task.project_id == pid)).all() == []  # nothing yet
    approval_service.approve(session, apr_id)
    approval_service.apply(session, apr_id)
    tasks = list(session.exec(select(Task).where(Task.project_id == pid)).all())
    assert len(tasks) == 1 and tasks[0].title == "via approval"
