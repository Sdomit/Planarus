"""#184: every MCP tool declares an outputSchema, and real handler output must
actually validate against it.

This is the regression that matters: the SDK's own call_tool decorator runs
``jsonschema.validate(instance=structuredContent, schema=tool.outputSchema)``
and turns a mismatch into an "Output validation error" for every single call —
so a wrong schema does not fail loudly at authoring time, it silently breaks
the tool in production. Every test below calls the real handler with seeded
data (not a hand-written fixture dict) and validates the real
``ToolResult.metadata`` it returns.
"""
from __future__ import annotations

import jsonschema
from app.mcp import output_schemas
from app.mcp.registry import PROPOSE_TOOLS, READ_TOOLS
from app.mcp.tools import propose, read
from app.schemas.blocker import BlockerCreate
from app.schemas.decision import DecisionCreate
from app.schemas.doc import DocCreate
from app.schemas.phase import PhaseCreate
from app.schemas.risk import RiskCreate
from app.schemas.task import TaskCreate
from app.services import (
    blocker_service,
    decision_service,
    doc_service,
    phase_service,
    risk_service,
    task_service,
)
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.mcp_util import EXPECTED_ALL_TOOLS, propose_cap, read_cap, seed


def _validate(metadata: dict, schema: dict) -> None:
    jsonschema.validate(instance=metadata, schema=schema)


# --- every tool has exactly one schema, and every schema is itself valid -----


def test_every_tool_has_an_output_schema() -> None:
    for name, spec in {**READ_TOOLS, **PROPOSE_TOOLS}.items():
        assert spec.output_schema, f"{name} has no output_schema"


def test_every_declared_schema_is_itself_valid_json_schema() -> None:
    validator_cls = jsonschema.validators.validator_for({})
    seen = set()
    for spec in {**READ_TOOLS, **PROPOSE_TOOLS}.values():
        key = id(spec.output_schema)
        if key in seen:
            continue
        seen.add(key)
        validator_cls.check_schema(spec.output_schema)


def test_schema_module_covers_exactly_the_registered_tools() -> None:
    """Catches an added tool that forgot a schema, and a stale schema left
    behind for a removed one."""
    assert {**READ_TOOLS, **PROPOSE_TOOLS}.keys() == EXPECTED_ALL_TOOLS


# --- read tools: seed one of everything, call each, validate ----------------


def test_list_projects_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os2")
    cap = read_cap(ws, pid)
    res = read.list_projects(session, cap, read.ListProjectsArgs())
    _validate(res.metadata, output_schemas.LIST_PROJECTS)


def test_get_active_work_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os3")
    phase = phase_service.create_phase(session, pid, PhaseCreate(title="Discovery"))
    task_service.create_task(session, pid, TaskCreate(title="t", status="in_progress", phase_id=phase.id))
    decision_service.create_decision(session, pid, DecisionCreate(title="D", decision="Do X", phase_id=phase.id))
    risk_service.create_risk(session, pid, RiskCreate(title="R", severity="high", phase_id=phase.id))
    blocker_service.create_blocker(session, pid, BlockerCreate(title="waiting"))
    cap = read_cap(ws, pid)
    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    _validate(res.metadata, output_schemas.GET_ACTIVE_WORK)


def test_get_active_work_output_matches_schema_when_empty(client: TestClient, session: Session) -> None:
    """The all-null/empty path — active_phase_id null, empty arrays — must
    still validate; this is exactly the shape a brand-new project returns."""
    ws, pid = seed(client, "os3b")
    cap = read_cap(ws, pid)
    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    assert res.metadata["active_phase_id"] is None
    _validate(res.metadata, output_schemas.GET_ACTIVE_WORK)


def test_get_project_summary_output_matches_schema_direct(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os4")
    cap = read_cap(ws, pid)
    res = read.get_project_summary(session, cap, read.ProjectArgs(project_id=pid))
    _validate(res.metadata, output_schemas.GET_PROJECT_SUMMARY)


def test_list_tasks_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os5")
    task_service.create_task(session, pid, TaskCreate(title="t"))
    cap = read_cap(ws, pid)
    res = read.list_tasks(session, cap, read.ListTasksArgs(project_id=pid))
    _validate(res.metadata, output_schemas.LIST_TASKS)


def test_list_decisions_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os6")
    decision_service.create_decision(session, pid, DecisionCreate(title="D", decision="Do X"))
    cap = read_cap(ws, pid)
    # phase_id omitted -> None, exercising the nullable path
    res = read.list_decisions(session, cap, read.ListPhaseScopedArgs(project_id=pid))
    _validate(res.metadata, output_schemas.LIST_DECISIONS)


def test_list_risks_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os7")
    risk_service.create_risk(session, pid, RiskCreate(title="R", severity="high"))
    cap = read_cap(ws, pid)
    res = read.list_risks(session, cap, read.ListPhaseScopedArgs(project_id=pid))
    _validate(res.metadata, output_schemas.LIST_RISKS)


def test_list_docs_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os8")
    doc_service.create_doc(session, pid, DocCreate(title="Doc", doc_type="note"))
    cap = read_cap(ws, pid)
    res = read.list_docs(session, cap, read.ListScopedArgs(project_id=pid))
    _validate(res.metadata, output_schemas.LIST_DOCS)


def test_get_doc_excerpt_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os9")
    doc = doc_service.create_doc(session, pid, DocCreate(title="Doc", doc_type="note"))
    cap = read_cap(ws, pid)
    res = read.get_doc_excerpt(session, cap, read.DocExcerptArgs(doc_id=doc.id))
    _validate(res.metadata, output_schemas.GET_DOC_EXCERPT)


def test_get_item_output_matches_schema_for_every_kind(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os10")
    task = task_service.create_task(session, pid, TaskCreate(title="t"))
    decision = decision_service.create_decision(session, pid, DecisionCreate(title="D", decision="Do X"))
    risk = risk_service.create_risk(session, pid, RiskCreate(title="R", severity="high"))
    doc = doc_service.create_doc(session, pid, DocCreate(title="Doc", doc_type="note"))
    cap = read_cap(ws, pid)
    for kind, item_id in (
        ("task", task.id),
        ("decision", decision.id),
        ("risk", risk.id),
        ("doc", doc.id),
    ):
        res = read.get_item(session, cap, read.GetItemArgs(kind=kind, item_id=item_id))
        _validate(res.metadata, output_schemas.GET_ITEM)


def test_get_approval_status_output_matches_schema_before_apply(
    client: TestClient, session: Session
) -> None:
    """Before apply, applied_entity_type/applied_entity_id are null — the
    common case, since most polls happen while a proposal is still pending."""
    ws, pid = seed(client, "os11")
    pcap = propose_cap(ws, pid)
    created = propose.create_task_proposal(
        session, pcap, propose.CreateTaskProposalArgs(project_id=pid, title="t")
    )
    rcap = read_cap(ws, pid)
    res = read.get_approval_status(
        session, rcap, read.ApprovalStatusArgs(approval_id=created.metadata["approval_id"])
    )
    assert res.metadata["applied_entity_type"] is None
    _validate(res.metadata, output_schemas.GET_APPROVAL_STATUS)


# --- propose tools: all five share one schema --------------------------------


def test_create_task_proposal_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os12")
    cap = propose_cap(ws, pid)
    res = propose.create_task_proposal(session, cap, propose.CreateTaskProposalArgs(project_id=pid, title="t"))
    _validate(res.metadata, output_schemas.CREATE_TASK_PROPOSAL)


def test_update_task_proposal_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os13")
    task = task_service.create_task(session, pid, TaskCreate(title="t"))
    cap = propose_cap(ws, pid)
    res = propose.update_task_proposal(
        session, cap, propose.UpdateTaskProposalArgs(task_id=task.id, title="t2")
    )
    _validate(res.metadata, output_schemas.UPDATE_TASK_PROPOSAL)


def test_create_decision_proposal_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os14")
    cap = propose_cap(ws, pid)
    res = propose.create_decision_proposal(
        session, cap, propose.CreateDecisionProposalArgs(project_id=pid, title="D", decision="Do X")
    )
    _validate(res.metadata, output_schemas.CREATE_DECISION_PROPOSAL)


def test_update_canvas_proposal_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os15")
    canvas = doc_service.create_doc(
        session, pid, DocCreate(title="C", doc_type="note", editor_format="excalidraw")
    )
    cap = propose_cap(ws, pid)
    res = propose.update_canvas_proposal(
        session,
        cap,
        propose.UpdateCanvasProposalArgs(doc_id=canvas.id, content_json="{}"),
    )
    _validate(res.metadata, output_schemas.UPDATE_CANVAS_PROPOSAL)


def test_create_connection_proposal_output_matches_schema(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "os16")
    a = task_service.create_task(session, pid, TaskCreate(title="a"))
    b = task_service.create_task(session, pid, TaskCreate(title="b"))
    cap = propose_cap(ws, pid)
    res = propose.create_connection_proposal(
        session,
        cap,
        propose.CreateConnectionProposalArgs(
            project_id=pid,
            relation_type="related_to",
            source_entity_type="task",
            source_entity_id=a.id,
            target_entity_type="task",
            target_entity_id=b.id,
        ),
    )
    _validate(res.metadata, output_schemas.CREATE_CONNECTION_PROPOSAL)
