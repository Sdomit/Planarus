"""Phase 7A approval engine tests: state machine, binding, security, audit.

Proposals are created through the internal service seam (there is no HTTP
proposal-creation endpoint in 7A). State changes go through the HTTP API with the
local control token, exercising the real route + dependency stack.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.exceptions import PolicyError, SecretDetectedError
from app.core.utils import new_id, now_utc, now_utc_plus_hours
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.decision import Decision
from app.models.project import Project
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import approval_service, task_service

_PAST = "2000-01-01T00:00:00+00:00"


def _seed(client: TestClient, suffix: str = "apr") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def _hdr(client: TestClient) -> dict:
    token = client.get("/api/v1/local-session").json()["token"]
    return {"X-AgentBoard-Local-Token": token}


def _propose_task_create(session: Session, pid: str, **patch) -> ApprovalRequest:
    patch.setdefault("title", "New task")
    return approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch=patch
    )


# --- local control token ------------------------------------------------------


def test_local_session_returns_token(client: TestClient) -> None:
    res = client.get("/api/v1/local-session")
    assert res.status_code == 200
    assert isinstance(res.json()["token"], str)
    assert len(res.json()["token"]) > 16


def test_local_session_rejects_foreign_origin(client: TestClient) -> None:
    res = client.get("/api/v1/local-session", headers={"Origin": "http://evil.example"})
    assert res.status_code == 403


def test_state_change_missing_token_401(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    res = client.post(f"/api/v1/approvals/{ar.id}/approve")
    assert res.status_code == 401


def test_state_change_bad_token_401(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    res = client.post(
        f"/api/v1/approvals/{ar.id}/approve",
        headers={"X-AgentBoard-Local-Token": "wrong"},
    )
    assert res.status_code == 401


def test_state_change_foreign_origin_403(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    headers = {**_hdr(client), "Origin": "http://evil.example"}
    res = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=headers)
    assert res.status_code == 403


def test_state_change_allowed_origin_ok(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    headers = {**_hdr(client), "Origin": "http://localhost:5173"}
    res = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=headers)
    assert res.status_code == 200


# --- no external write surface ------------------------------------------------


def test_no_http_proposal_creation_endpoint(client: TestClient) -> None:
    pid = _seed(client)
    r1 = client.post(
        "/api/v1/approvals",
        json={"action_type": "task.create", "project_id": pid, "patch": {"title": "x"}},
    )
    assert r1.status_code in (404, 405)
    r2 = client.post(f"/api/v1/projects/{pid}/approvals", json={"title": "x"})
    assert r2.status_code in (404, 405)


# --- creation + binding -------------------------------------------------------


def test_create_proposal_pending(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid, title="T", status="ready")
    assert ar.id.startswith("apr_")
    assert ar.status == "pending"
    assert ar.action_type == "task.create"
    assert ar.policy_version == approval_service.allowlist.POLICY_VERSION
    assert ar.patch_checksum
    events = approval_service.get_proposal_audit(session, ar.id)
    assert [e.event_type for e in events] == ["proposal_created"]


def test_unknown_action_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(PolicyError):
        approval_service.create_proposal(
            session, project_id=pid, action_type="task.delete", patch={"title": "x"}
        )


def test_unknown_field_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(PolicyError):
        _propose_task_create(session, pid, title="t", bogus="x")


def test_forbidden_field_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(PolicyError):
        _propose_task_create(session, pid, title="t", project_id="hack")


def test_invalid_status_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(PolicyError):
        _propose_task_create(session, pid, title="t", status="not-a-status")


def test_cross_project_target_rejected(client: TestClient, session: Session) -> None:
    pid_a = _seed(client, "a")
    pid_b = _seed(client, "b")
    task_b = task_service.create_task(session, pid_b, TaskCreate(title="b task"))
    with pytest.raises(PolicyError):
        approval_service.create_proposal(
            session,
            project_id=pid_a,
            action_type="task.update",
            target_entity_id=task_b.id,
            patch={"title": "x"},
        )


def test_invalid_phase_dependency_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(PolicyError):
        _propose_task_create(session, pid, title="t", phase_id="ph_nope")


def test_oversized_patch_rejected(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(PolicyError):
        _propose_task_create(session, pid, title="a" * 70000)


def test_update_target_not_found_raises(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    with pytest.raises(LookupError):
        approval_service.create_proposal(
            session,
            project_id=pid,
            action_type="task.update",
            target_entity_id="tsk_missing",
            patch={"title": "x"},
        )


# --- secrets ------------------------------------------------------------------


def test_secret_proposal_rejected_no_raw_value(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    secret = "AKIAIOSFODNN7EXAMPLE"
    with pytest.raises(SecretDetectedError) as exc:
        _propose_task_create(session, pid, title=f"key {secret}")
    assert secret not in str(exc.value)
    # No proposal row was created, and no audit row carries the raw value.
    assert session.exec(select(ApprovalRequest)).all() == []
    for ev in session.exec(select(AuditEvent)).all():
        assert secret not in (ev.payload_json or "")


# --- happy path ---------------------------------------------------------------


def test_approve_then_apply_task_create(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid, title="New task", status="ready")

    ra = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    assert ra.status_code == 200 and ra.json()["status"] == "approved"

    rp = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert rp.status_code == 200 and rp.json()["status"] == "applied"

    tasks = list(session.exec(select(Task).where(Task.project_id == pid)).all())
    assert len(tasks) == 1
    assert tasks[0].title == "New task" and tasks[0].status == "ready"

    refreshed = session.get(ApprovalRequest, ar.id)
    assert refreshed.applied_at is not None
    assert refreshed.applied_audit_event_id is not None


def test_apply_decision_create(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="decision.create",
        patch={"title": "D", "decision": "Decided"},
    )
    client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    decs = list(session.exec(select(Decision).where(Decision.project_id == pid)).all())
    assert len(decs) == 1 and decs[0].decision == "Decided"


def test_apply_task_update(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    task = task_service.create_task(session, pid, TaskCreate(title="orig", status="backlog"))
    ar = approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="task.update",
        target_entity_id=task.id,
        patch={"title": "updated", "status": "in_progress"},
    )
    client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    refreshed = session.get(Task, task.id)
    assert refreshed.title == "updated" and refreshed.status == "in_progress"


# --- one-time apply / replay --------------------------------------------------


def test_apply_is_one_time(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    r1 = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert r1.status_code == 200
    r2 = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert r2.status_code == 409
    assert len(list(session.exec(select(Task).where(Task.project_id == pid)).all())) == 1


# --- invalid transitions ------------------------------------------------------


def test_apply_requires_approved(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409


def test_reject_then_approve_conflict(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    client.post(f"/api/v1/approvals/{ar.id}/reject", headers=_hdr(client), json={"reason": "no"})
    res = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "rejected"


def test_approve_after_apply_conflict(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    res = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    assert res.status_code == 409


def test_apply_after_reject_conflict(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    client.post(f"/api/v1/approvals/{ar.id}/reject", headers=_hdr(client))
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409


def test_reject_records_reason(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    res = client.post(
        f"/api/v1/approvals/{ar.id}/reject", headers=_hdr(client), json={"reason": "duplicate"}
    )
    assert res.status_code == 200 and res.json()["status"] == "rejected"
    assert session.get(ApprovalRequest, ar.id).reason == "duplicate"


def test_invalidate(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    res = client.post(f"/api/v1/approvals/{ar.id}/invalidate", headers=_hdr(client))
    assert res.status_code == 200 and res.json()["status"] == "invalidated"


# --- expiry -------------------------------------------------------------------


def test_expired_cannot_be_approved(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    row = session.get(ApprovalRequest, ar.id)
    row.expires_at = _PAST
    session.add(row)
    session.commit()
    res = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "expired"


def test_expired_cannot_be_applied(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    approval_service.approve(session, ar.id)
    row = session.get(ApprovalRequest, ar.id)
    row.expires_at = _PAST
    session.add(row)
    session.commit()
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "expired"


def test_default_expiry_is_24h(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    assert ar.expires_at > now_utc()  # in the future
    assert ar.expires_at <= now_utc_plus_hours(approval_service.APPROVAL_TTL_HOURS + 1)


# --- stale-state protection ---------------------------------------------------


def test_approve_stale_target_invalidates(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    task = task_service.create_task(session, pid, TaskCreate(title="orig"))
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.update",
        target_entity_id=task.id, patch={"title": "proposed"},
    )
    task_service.update_task(session, task.id, TaskUpdate(title="edited"))
    res = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "invalidated"


def test_apply_stale_target_invalidates(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    task = task_service.create_task(session, pid, TaskCreate(title="orig"))
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.update",
        target_entity_id=task.id, patch={"title": "proposed"},
    )
    approval_service.approve(session, ar.id)
    task_service.update_task(session, task.id, TaskUpdate(title="edited"))
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "invalidated"
    # canonical state untouched by the stale proposal
    assert session.get(Task, task.id).title == "edited"


def test_patch_checksum_mismatch_invalidates(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid, title="good")
    approval_service.approve(session, ar.id)
    row = session.get(ApprovalRequest, ar.id)
    row.proposed_patch_json = '{"title":"tampered"}'  # checksum left stale
    session.add(row)
    session.commit()
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "invalidated"
    assert session.exec(select(Task).where(Task.project_id == pid)).all() == []


def test_policy_version_mismatch_invalidates(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid, title="good")
    approval_service.approve(session, ar.id)
    row = session.get(ApprovalRequest, ar.id)
    row.policy_version = 999
    session.add(row)
    session.commit()
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "invalidated"


def test_apply_dependency_deleted_invalidates(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "P1"}).json()
    ar = _propose_task_create(session, pid, title="t", phase_id=phase["id"])
    approval_service.approve(session, ar.id)
    # Delete the phase out from under the approved proposal.
    from app.models.phase import Phase

    session.delete(session.get(Phase, phase["id"]))
    session.commit()
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 409
    assert session.get(ApprovalRequest, ar.id).status == "invalidated"


# --- failure + retry ----------------------------------------------------------


def test_failed_apply_then_retry(client: TestClient, session: Session, monkeypatch) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid, title="X")
    approval_service.approve(session, ar.id)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(approval_service.handlers, "apply_action", _boom)
    res = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res.status_code == 500
    failed = session.get(ApprovalRequest, ar.id)
    assert failed.status == "failed" and failed.failure_reason
    assert session.exec(select(Task).where(Task.project_id == pid)).all() == []
    audit_types = [e.event_type for e in approval_service.get_proposal_audit(session, ar.id)]
    assert "proposal_apply_failed" in audit_types

    # Full revalidation on retry; now it succeeds.
    monkeypatch.undo()
    res2 = client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    assert res2.status_code == 200
    assert session.get(ApprovalRequest, ar.id).status == "applied"
    assert len(list(session.exec(select(Task).where(Task.project_id == pid)).all())) == 1


# --- audit --------------------------------------------------------------------


def test_one_audit_event_per_transition(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    client.post(f"/api/v1/approvals/{ar.id}/apply", headers=_hdr(client))
    events = approval_service.get_proposal_audit(session, ar.id)
    types = [e.event_type for e in events]
    assert types.count("proposal_created") == 1
    assert types.count("proposal_approved") == 1
    assert types.count("proposal_applied") == 1
    assert len(events) == 3


def test_audit_excludes_patch_values(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    _propose_task_create(session, pid, title="SENTINELTITLE", description="SENTINELDESC")
    for ev in session.exec(select(AuditEvent)).all():
        body = ev.payload_json or ""
        assert "SENTINELTITLE" not in body
        assert "SENTINELDESC" not in body


def test_audit_endpoint_returns_timeline(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    ar = _propose_task_create(session, pid)
    client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_hdr(client))
    res = client.get(f"/api/v1/approvals/{ar.id}/audit")
    assert res.status_code == 200
    kinds = [e["event_type"] for e in res.json()]
    assert "proposal_created" in kinds and "proposal_approved" in kinds


# --- list / detail ------------------------------------------------------------


def test_list_and_detail(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    task = task_service.create_task(session, pid, TaskCreate(title="orig"))
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.update",
        target_entity_id=task.id, patch={"title": "new title"},
    )
    listed = client.get(f"/api/v1/approvals?project_id={pid}").json()
    assert any(a["id"] == ar.id for a in listed)

    detail = client.get(f"/api/v1/approvals/{ar.id}").json()
    assert detail["patch_checksum"] == ar.patch_checksum
    diff = {d["field"]: d for d in detail["diff"]}
    assert diff["title"]["before"] == "orig"
    assert diff["title"]["after"] == "new title"
    assert detail["is_expired"] is False


def test_detail_missing_404(client: TestClient) -> None:
    assert client.get("/api/v1/approvals/apr_missing").status_code == 404


def test_approve_missing_404(client: TestClient) -> None:
    res = client.post("/api/v1/approvals/apr_missing/approve", headers=_hdr(client))
    assert res.status_code == 404


# --- model constraint ---------------------------------------------------------


def test_model_status_check_constraint(client: TestClient, session: Session) -> None:
    pid = _seed(client)
    project = session.get(Project, pid)
    bad = ApprovalRequest(
        id=new_id("apr"),
        workspace_id=project.workspace_id,
        project_id=pid,
        origin="local",
        action_type="task.create",
        proposed_patch_json="{}",
        patch_checksum="x",
        policy_version=1,
        risk_level="low",
        status="bogus-state",
        created_at=now_utc(),
        expires_at=now_utc_plus_hours(24),
    )
    session.add(bad)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
