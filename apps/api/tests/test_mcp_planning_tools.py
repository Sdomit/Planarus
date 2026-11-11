"""New planning MCP tools retain the same read/propose/approve boundary."""
import pytest
from app.mcp.errors import CODE_FORBIDDEN, CODE_INVALID, MCPToolError
from app.mcp.tools import propose, read
from app.models.comment import Comment
from app.models.decision import Decision
from app.models.link import Link
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.risk import Risk
from app.services import approval_service
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.mcp_util import propose_cap, read_cap, seed


def _apply(session: Session, approval_id: str):
    approval_service.approve(session, approval_id)
    return approval_service.apply(session, approval_id)


def test_phase_milestone_risk_and_comment_are_proposals(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "planning-tools")
    cap = propose_cap(ws, pid)
    for kind, default in (("phase", "planned"), ("milestone", "planned"), ("risk", "open")):
        options = read.list_status_options(
            session, cap, read.ListStatusOptionsArgs(project_id=pid, entity_type=kind)
        )
        assert options.metadata["default_status"] == default
        assert default in options.metadata["status_keys"]
    phase_receipt = propose.create_phase_proposal(
        session, cap, propose.CreatePhaseProposalArgs(project_id=pid, title="Build")
    )
    assert phase_receipt.metadata["status"] == "pending"
    assert session.exec(select(Phase).where(Phase.project_id == pid)).all() == []
    _apply(session, phase_receipt.metadata["approval_id"])
    phase_id = session.exec(select(Phase).where(Phase.project_id == pid)).one().id

    milestone_receipt = propose.create_milestone_proposal(
        session, cap, propose.CreateMilestoneProposalArgs(
            project_id=pid, title="First release", phase_id=phase_id, target_date="2026-12-01"
        )
    )
    risk_receipt = propose.create_risk_proposal(
        session, cap, propose.CreateRiskProposalArgs(
            project_id=pid, title="Delay", severity="high", phase_id=phase_id
        )
    )
    comment_receipt = propose.create_comment_proposal(
        session, cap, propose.CreateCommentProposalArgs(
            project_id=pid, entity_type="phase", entity_id=phase_id, body="Review scope"
        )
    )
    assert session.exec(select(Milestone).where(Milestone.project_id == pid)).all() == []
    assert session.exec(select(Risk).where(Risk.project_id == pid)).all() == []
    assert session.exec(select(Comment).where(Comment.project_id == pid)).all() == []
    for receipt in (milestone_receipt, risk_receipt, comment_receipt):
        _apply(session, receipt.metadata["approval_id"])

    link_receipt = propose.create_link_proposal(
        session, cap, propose.CreateLinkProposalArgs(
            project_id=pid, entity_type="phase", entity_id=phase_id,
            url="https://example.org/plan", title="Plan source",
        )
    )
    assert session.exec(select(Link).where(Link.project_id == pid)).all() == []
    _apply(session, link_receipt.metadata["approval_id"])

    milestone_id = session.exec(select(Milestone).where(Milestone.project_id == pid)).one().id
    connection_receipt = propose.create_connection_proposal(
        session, cap, propose.CreateConnectionProposalArgs(
            project_id=pid, relation_type="related_to",
            source_entity_type="phase", source_entity_id=phase_id,
            target_entity_type="milestone", target_entity_id=milestone_id,
        )
    )
    _apply(session, connection_receipt.metadata["approval_id"])

    assert read.list_phases(session, cap, read.ListScopedArgs(project_id=pid)).metadata["phase_ids"] == [phase_id]
    assert read.list_milestones(session, cap, read.ListPhaseScopedArgs(project_id=pid)).metadata["count"] == 1
    assert read.list_risks(session, cap, read.ListPhaseScopedArgs(project_id=pid)).metadata["count"] == 1
    assert read.list_comments(session, cap, read.ListCommentsArgs(project_id=pid)).metadata["count"] == 1
    assert read.list_links(session, cap, read.ListCommentsArgs(project_id=pid)).metadata["count"] == 1
    connections = read.list_connections(session, cap, read.ListScopedArgs(project_id=pid))
    assert set(connections.metadata["source_entity_ids"] + connections.metadata["target_entity_ids"]) == {
        phase_id, milestone_id,
    }
    assert session.exec(select(Comment).where(Comment.project_id == pid)).one().author_type == "agent"


def test_new_tools_reject_wrong_scope_and_invalid_references(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "planning-scope")
    _, other = seed(client, "planning-other")
    cap = propose_cap(ws, pid)
    with pytest.raises(MCPToolError) as exc:
        propose.create_phase_proposal(
            session, cap, propose.CreatePhaseProposalArgs(project_id=other, title="Wrong")
        )
    assert exc.value.code == CODE_FORBIDDEN
    with pytest.raises(MCPToolError) as exc:
        propose.create_comment_proposal(
            session, cap, propose.CreateCommentProposalArgs(
                project_id=pid, entity_type="phase", entity_id="ph_missing", body="Wrong"
            )
        )
    assert exc.value.code == CODE_INVALID
    with pytest.raises(MCPToolError) as exc:
        propose.create_risk_proposal(
            session, cap, propose.CreateRiskProposalArgs(
                project_id=pid, title="Wrong", severity="extreme"
            )
        )
    assert exc.value.code == CODE_INVALID
    with pytest.raises(MCPToolError) as exc:
        propose.create_milestone_proposal(
            session, cap, propose.CreateMilestoneProposalArgs(
                project_id=pid, title="Wrong", status="todo"
            )
        )
    assert exc.value.code == CODE_INVALID
    with pytest.raises(MCPToolError) as exc:
        read.list_comments(session, read_cap(ws, pid), read.ListCommentsArgs(project_id=other))
    assert exc.value.code == CODE_FORBIDDEN
    with pytest.raises(MCPToolError) as exc:
        propose.create_link_proposal(
            session, cap, propose.CreateLinkProposalArgs(
                project_id=pid, entity_type="project", entity_id=pid,
                url="javascript:alert(1)",
            )
        )
    assert exc.value.code == CODE_INVALID


def test_update_proposals_change_existing_records_only_after_apply(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "planning-updates")
    cap = propose_cap(ws, pid)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Plan"}).json()
    milestone = client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "Ship"}).json()
    risk = client.post(f"/api/v1/projects/{pid}/risks", json={"title": "Slip", "severity": "low"}).json()
    decision = client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "Choose", "decision": "Old"}).json()
    cases = (
        (propose.update_phase_proposal, propose.UpdatePhaseProposalArgs(phase_id=phase["id"], title="Execute"), Phase, phase["id"], "title", "Execute"),
        (propose.update_milestone_proposal, propose.UpdateMilestoneProposalArgs(milestone_id=milestone["id"], status="active"), Milestone, milestone["id"], "status", "active"),
        (propose.update_risk_proposal, propose.UpdateRiskProposalArgs(risk_id=risk["id"], severity="high"), Risk, risk["id"], "severity", "high"),
        (propose.update_decision_proposal, propose.UpdateDecisionProposalArgs(decision_id=decision["id"], decision="New"), Decision, decision["id"], "decision", "New"),
    )
    for tool, args, model, target_id, field, expected in cases:
        before = getattr(session.get(model, target_id), field)
        receipt = tool(session, cap, args)
        assert receipt.metadata["status"] == "pending"
        assert getattr(session.get(model, target_id), field) == before
        _apply(session, receipt.metadata["approval_id"])
        assert getattr(session.get(model, target_id), field) == expected
