"""Seed a running Planarus database with a demo project (dogfooding, take two).

``seed_planarus_project.py`` loads the real, live Planarus roadmap (phases +
milestones only — that project keeps getting worked in the app, so the seed
stays minimal on purpose). This script is different: it creates a *separate*,
throwaway-safe **"Planarus Demo"** project that exercises every planning
entity the tool has — phases, stages, tasks with subtasks and checklists,
milestones, risks, blockers, decisions, docs of every type, comments, todos,
links, calendar events, entity connections, a custom status option, and agent
run telemetry — so a new user (or teammate) can open one project and see the
whole feature surface at once.

The content is not Lorem Ipsum: it retells Planarus's own build story (SQLite
→ Postgres, the approval-gated AI surfaces, the #103 unbounded-query fix, the
#122 IaC retirement, the #111 release-readiness audit) using the real phase
names, issue numbers, and dates from context/NEXT_STEP.md and CLAUDE.md at
the time this script was written. Treat the numbers as a snapshot, not a
live sync — this file does not read the roadmap docs, it just quotes them.

Idempotent at the project level: if ``planarus-demo`` already exists, does
nothing (re-running is safe). Run against a **migrated** DB — the app applies
migrations on startup, or run ``alembic upgrade head`` first. Honors
``PLANARUS_DATABASE_URL`` / ``DATABASE_URL`` like the rest of the app.

    cd apps/api && python scripts/seed_demo_project.py
"""
import json
import sys

from app.db.session import engine
from app.models.project import Project
from app.models.workspace import Workspace
from app.schemas.agent_run import AgentRunCreate
from app.schemas.blocker import BlockerCreate
from app.schemas.calendar_event import CalendarEventCreate
from app.schemas.checklist_item import ChecklistItemCreate
from app.schemas.comment import CommentCreate
from app.schemas.decision import DecisionCreate
from app.schemas.doc import DocCreate, DocUpdate
from app.schemas.entity_connection import EntityConnectionCreate
from app.schemas.link import LinkCreate
from app.schemas.milestone import MilestoneCreate
from app.schemas.phase import PhaseCreate
from app.schemas.project import ProjectCreate
from app.schemas.risk import RiskCreate
from app.schemas.stage import StageCreate
from app.schemas.status_option import StatusOptionCreate
from app.schemas.task import TaskCreate
from app.schemas.todo import TodoCreate
from app.schemas.workspace import WorkspaceCreate
from app.services import (
    agent_run_service,
    blocker_service,
    calendar_event_service,
    checklist_service,
    comment_service,
    decision_service,
    doc_service,
    entity_connection_service,
    link_service,
    milestone_service,
    phase_service,
    project_service,
    risk_service,
    stage_service,
    status_option_service,
    task_service,
    todo_service,
    workspace_service,
)
from sqlmodel import Session, select

WORKSPACE_SLUG = "planarus-demo"
PROJECT_SLUG = "planarus-demo"
REPO = "https://github.com/Sdomit/Planarus"


def _tiptap(*lines: str) -> tuple[str, str]:
    """Build (content_json, markdown_cache) for a simple Tiptap doc.

    ``## `` prefixes a heading, ``- `` a single-item bullet list, anything else
    a paragraph. Good enough for demo prose; not a Markdown parser.
    """
    nodes: list[dict] = []
    md: list[str] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("## "):
            text = line[3:]
            nodes.append(
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": text}]}
            )
            md.append(f"## {text}")
        elif line.startswith("- "):
            text = line[2:]
            nodes.append(
                {
                    "type": "bulletList",
                    "content": [
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}
                    ],
                }
            )
            md.append(f"- {text}")
        else:
            nodes.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
            md.append(line)
    return json.dumps({"type": "doc", "content": nodes}), "\n\n".join(md)


def _seed(session: Session) -> Project:
    # Seed into the FIRST existing workspace, not a dedicated demo one: the web
    # dashboard hardcodes `workspaces[0]` and filters projects by it, with no
    # workspace switcher in the UI. A project in any other workspace is created
    # correctly and is simply unreachable in the app — which for a demo whose
    # whole job is being looked at, is the same as not existing.
    ws = session.exec(select(Workspace)).first()
    if ws is None:
        ws = workspace_service.create_workspace(
            session,
            WorkspaceCreate(
                name="Planarus Demo",
                slug=WORKSPACE_SLUG,
                description="Sandbox workspace for the feature-tour demo project.",
            ),
        )

    project = project_service.create_project(
        session,
        ProjectCreate(
            workspace_id=ws.id,
            title="Planarus Demo — How We Built Planarus",
            slug=PROJECT_SLUG,
            summary=(
                "A tour of every Planarus feature, told through Planarus's own build "
                "history: phases, tasks, docs, risks, decisions, and the real fixes "
                "behind issues #103, #111, #119 and #122."
            ),
            status="active",
        ),
    )
    pid = project.id

    # ---- Phases (condensed real arc) --------------------------------------
    phases = {}
    for key, title, status in [
        ("foundation", "Phase 1-2 — Foundation: runnable app + SQLite", "done"),
        ("core", "Phase 4-7 — Planning core: phases, tasks, docs, approvals", "done"),
        ("ai", "Phase 7B-7C — AI surfaces: MCP + external API, approval-gated", "done"),
        ("team", "Phase 10-11 — Team & hosted groundwork: LAN mode, admin, integrations", "done"),
        ("graph", "Phase 15-19 — Planning graph: boards, roadmap, calendar, connections", "active"),
        ("release", "Release readiness — audit, IaC cleanup, public launch", "blocked"),
    ]:
        phases[key] = phase_service.create_phase(session, pid, PhaseCreate(title=title, status=status))

    # ---- Stages (under the active phase) -----------------------------------
    stages = {}
    for key, title, status in [
        ("statuses", "Custom statuses & board columns (#88)", "done"),
        ("connections", "Entity connections & dependency graph (#94)", "active"),
        ("calsync", "Calendar sync (Google / Microsoft)", "planned"),
    ]:
        stages[key] = stage_service.create_stage(
            session, pid, StageCreate(phase_id=phases["graph"].id, title=title, status=status)
        )

    # ---- Custom status option (task board column demo) --------------------
    status_option_service.create_status_option(
        session,
        pid,
        StatusOptionCreate(entity_type="task", label="Shipped \U0001f680", category="done", color="#22c55e"),
    )

    # ---- Tasks: statuses, priorities, subtasks, custom status -------------
    mcp_parent = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Ship the approval-gated MCP server",
            description="STDIO MCP transport that lets an agent read context and propose writes — nothing lands without a human approval.",
            status="in_progress",
            priority="high",
            phase_id=phases["ai"].id,
        ),
    )
    sub_diff = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Implement diff + policy checks",
            status="in_progress",
            priority="high",
            phase_id=phases["ai"].id,
            parent_task_id=mcp_parent.id,
        ),
    )
    sub_tests = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Write STDIO transport tests",
            status="backlog",
            priority="med",
            phase_id=phases["ai"].id,
            parent_task_id=mcp_parent.id,
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Draft ApprovalRequest state machine",
            status="done",
            priority="high",
            phase_id=phases["ai"].id,
            parent_task_id=mcp_parent.id,
        ),
    )

    task_notif = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Batch the notification feed query (#103)",
            description="N+1 query per notification row — batch-loaded instead, so the feed stays flat under load.",
            status="done",
            priority="urgent",
            phase_id=phases["graph"].id,
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Window the calendar query in SQL (#103)",
            description="Was pulling every event into Python and filtering there; now windowed in the query itself.",
            status="done",
            priority="high",
            phase_id=phases["graph"].id,
        ),
    )

    task_iac = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Retire untested Terraform IaC modules (#122)",
            description="deploy/aws and deploy/azure never wrote PLANARUS_OAUTH_REDIRECT_URIS — an apply produced a box nobody could sign into.",
            status="done",
            priority="med",
            phase_id=phases["release"].id,
        ),
    )
    task_ghsupport = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="File GitHub Support ticket to purge stale pull refs (#119)",
            description="99 of 108 server-side refs/pull/* still reach the pre-rewrite history. Only a support-side purge removes them.",
            status="blocked",
            priority="urgent",
            phase_id=phases["release"].id,
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Draft release-readiness audit report (#111)",
            status="needs_review",
            priority="med",
            phase_id=phases["release"].id,
        ),
    )
    task_member = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Add member search + workspace claim",
            status="done",
            priority="low",
            phase_id=phases["team"].id,
        ),
    )
    task_customstatus = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Design custom status board columns (#88)",
            status="done",
            priority="med",
            phase_id=phases["graph"].id,
            stage_id=stages["statuses"].id,
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Plan Phase 14 hosted/SaaS mode",
            status="ready",
            priority="low",
            phase_id=phases["release"].id,
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Fix Flow board custom-status visibility (#97)",
            status="done",
            priority="high",
            phase_id=phases["graph"].id,
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Evaluate Kubernetes autoscaling for the API",
            description="Rejected: rate-limit buckets, the local control token, and LAN presence are all process-local state. See the hosted runtime contract decision below.",
            status="canceled",
            priority="low",
            phase_id=phases["release"].id,
        ),
    )
    task_shipped = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Ship the Cosmo brand rebrand",
            status="shipped",
            priority="med",
            phase_id=phases["team"].id,
        ),
    )

    # ---- Checklist items (under the custom-status-board task) --------------
    for label, done in [
        ("Define STATUS_CATEGORIES enum", True),
        ("Add status_option table + service", True),
        ("Wire board columns to custom statuses", True),
    ]:
        checklist_service.create_checklist_item(
            session, task_customstatus.id, ChecklistItemCreate(label=label, done=done)
        )

    # ---- Blocker ------------------------------------------------------------
    blocker_service.create_blocker(
        session,
        pid,
        BlockerCreate(
            title="Waiting on GitHub Support to purge 99 stale pull refs",
            description="That's the gate before any public-visibility flip — a support ticket, not code.",
            status="open",
            task_id=task_ghsupport.id,
        ),
    )

    # ---- Milestones -----------------------------------------------------------
    mil_mvp = milestone_service.create_milestone(
        session, pid, MilestoneCreate(title="MVP + V1 feature-complete", status="achieved")
    )
    mil_wave1 = milestone_service.create_milestone(
        session,
        pid,
        MilestoneCreate(title="Release-readiness Wave 1 closed", status="achieved", phase_id=phases["release"].id),
    )
    milestone_service.create_milestone(
        session,
        pid,
        MilestoneCreate(
            title="OSS public launch", status="planned", phase_id=phases["release"].id, target_date="2026-09-01"
        ),
    )
    milestone_service.create_milestone(
        session, pid, MilestoneCreate(title="Hosted SaaS beta", status="planned", phase_id=phases["release"].id)
    )

    # ---- Risks ------------------------------------------------------------
    risk_unbounded = risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="Unbounded queries slow down at scale (#103)",
            description="The notification feed and calendar view both scaled with row count instead of page size.",
            severity="high",
            status="mitigated",
            mitigation="Batched the notification feed and windowed the calendar query in SQL.",
            phase_id=phases["graph"].id,
        ),
    )
    risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="A second API replica would split local state",
            description="Rate-limit buckets, the local control token, and LAN presence are process-local.",
            severity="critical",
            status="accepted",
            mitigation="Hosted runtime contract: one process, one replica, autoscaling off — enforced by create_app() and scripts/doctor.py.",
            phase_id=phases["release"].id,
        ),
    )
    risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="Stale GitHub pull refs block public visibility (#119)",
            description="99 of 108 server-side refs/pull/* still reach the pre-rewrite commit.",
            severity="medium",
            status="monitoring",
            mitigation="Support ticket drafted; a purge is the only fix.",
            phase_id=phases["release"].id,
        ),
    )
    risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="Untested cloud IaC could provision an inaccessible box (#122)",
            description="Cloud-init scripts never wrote the mandatory OAuth redirect env var.",
            severity="high",
            status="closed",
            mitigation="Retired deploy/aws and deploy/azure entirely rather than hardening them.",
            phase_id=phases["release"].id,
        ),
    )

    # ---- Decisions ----------------------------------------------------------
    decision_service.create_decision(
        session,
        pid,
        DecisionCreate(
            title="Use SQLite for local mode, Postgres for hosted/LAN",
            context="Needed a zero-install local default and a real concurrent-write story for hosted deploys.",
            decision="One SQLModel schema targets both; Alembic migrations run against either.",
            status="accepted",
            phase_id=phases["foundation"].id,
        ),
    )
    decision_service.create_decision(
        session,
        pid,
        DecisionCreate(
            title="All AI-surface writes are approval-gated",
            context="MCP and the external API let agents propose changes; nothing should land unreviewed.",
            decision="Every write goes through ApprovalRequest: preview -> human approve -> commit.",
            status="accepted",
            phase_id=phases["ai"].id,
        ),
    )
    decision_iac = decision_service.create_decision(
        session,
        pid,
        DecisionCreate(
            title="Retire the Terraform IaC modules instead of hardening them (#122)",
            context="The AWS/Azure modules were untested and missing a mandatory env var.",
            decision="Delete deploy/aws and deploy/azure; keep the one CI-tested docker-compose.hosted.yml path.",
            status="accepted",
            phase_id=phases["release"].id,
        ),
    )
    decision_service.create_decision(
        session,
        pid,
        DecisionCreate(
            title="Cap hosted runtime at one API process, no autoscaling",
            context="Rate limits, the local control token, and LAN presence are all process-local state.",
            decision="create_app() and scripts/doctor.py fail closed above one worker.",
            status="accepted",
            phase_id=phases["release"].id,
        ),
    )

    # ---- Docs: one of each doc_type ----------------------------------------
    doc_tour = doc_service.create_doc(
        session, pid, DocCreate(title="Demo tour — how to use this project", doc_type="note", status="published")
    )
    content, md = _tiptap(
        "## Start here",
        "This project is a live tour of Planarus, seeded with the real story of how Planarus itself got built.",
        "- Open the Roadmap to see the phases and stages above",
        "- Open the Task Board to see statuses, priorities, subtasks and the custom \"Shipped\" column",
        "- Open Risks and Decisions to see the #103 / #119 / #122 write-ups",
        "- Open the Calendar for the recurring review sync and the launch date",
        "Everything here is disposable — delete the 'planarus-demo' project any time and re-run the seed script to reset it.",
    )
    doc_service.update_doc(session, doc_tour.id, DocUpdate(version=1, content_json=content, markdown_cache=md))

    content, md = _tiptap(
        "## Roadmap overview",
        "Planarus shipped in phases: a runnable foundation, then the planning core (phases/tasks/docs/approvals), then approval-gated AI surfaces (MCP + external API), then team and hosted groundwork, then the planning graph (boards, roadmap, calendar, connections).",
        "Release readiness is the current frontier: a 2026-07-24 audit returned NO-GO pending two waves of fixes, most of which are closed.",
    )
    doc_roadmap = doc_service.create_doc(session, pid, DocCreate(title="Roadmap overview", doc_type="plan", status="published"))
    doc_service.update_doc(session, doc_roadmap.id, DocUpdate(version=1, content_json=content, markdown_cache=md))

    content, md = _tiptap(
        "## Approval engine contract",
        "Every write proposed through an external AI surface (MCP, the HTTP API) is approval-gated: preview, then a human approves, then it commits.",
        "- ApprovalRequest carries a risk_level, a policy_version, and a diff",
        "- Expired or invalidated requests cannot be applied",
        "- Applying writes an audit event, always",
    )
    doc_spec = doc_service.create_doc(session, pid, DocCreate(title="Approval engine contract", doc_type="spec", status="published"))
    doc_service.update_doc(session, doc_spec.id, DocUpdate(version=1, content_json=content, markdown_cache=md))

    content, md = _tiptap(
        "## Why SQLite, then Postgres — not just Postgres",
        "Local-first means the app has to run with zero install. SQLite gives that for free.",
        "Hosted/LAN mode needs real concurrent writers, so the same schema targets Postgres there.",
        "One SQLModel layer, two engines, Alembic migrations that run against either.",
    )
    doc_research = doc_service.create_doc(session, pid, DocCreate(title="Why SQLite -> Postgres, not just Postgres", doc_type="research", status="published"))
    doc_service.update_doc(session, doc_research.id, DocUpdate(version=1, content_json=content, markdown_cache=md))

    content, md = _tiptap(
        "## Release-readiness audit findings (#111)",
        "The 2026-07-24 audit returned NO-GO — keep the repo private until the release blockers close.",
        "Wave 0 closed: #86, #87, #88, #89, #113, #114, #115, #119's history rewrite executed.",
        "Wave 1 closed: #124, #116, #117, #118, #120, #122.",
        "#119 stays open on one thing only: a GitHub Support purge of stale server-side pull refs.",
    )
    doc_audit = doc_service.create_doc(session, pid, DocCreate(title="Release-readiness audit findings (#111)", doc_type="reference", status="published"))
    doc_service.update_doc(session, doc_audit.id, DocUpdate(version=1, content_json=content, markdown_cache=md))

    doc_canvas = doc_service.create_doc(
        session, pid, DocCreate(title="Architecture sketch", doc_type="canvas", editor_format="excalidraw", status="draft")
    )

    # ---- Comments -----------------------------------------------------------
    comment_service.create_comment(
        session,
        pid,
        CommentCreate(
            entity_type="task",
            entity_id=task_ghsupport.id,
            body="Ticket drafted on the audit branch — filing this week.",
            author_type="human",
        ),
    )
    comment_service.create_comment(
        session,
        pid,
        CommentCreate(
            entity_type="decision",
            entity_id=decision_iac.id,
            body="Confirmed: no cloud-init script ever wrote PLANARUS_OAUTH_REDIRECT_URIS — that's the case for deleting rather than patching.",
            author_type="agent",
        ),
    )
    comment_service.create_comment(
        session,
        pid,
        CommentCreate(
            entity_type="doc",
            entity_id=doc_tour.id,
            body="Start here if this is your first time in Planarus.",
            author_type="human",
        ),
    )

    # ---- Todos (nested scratch list) ----------------------------------------
    todo_record = todo_service.create_todo(session, pid, TodoCreate(label="Record a 2-minute demo video"))
    todo_service.create_todo(
        session, pid, TodoCreate(label="Script the walkthrough", parent_id=todo_record.id, done=True)
    )
    todo_service.create_todo(
        session, pid, TodoCreate(label="Capture screen recording", parent_id=todo_record.id)
    )
    todo_service.create_todo(session, pid, TodoCreate(label="Share the demo project link with the team"))

    # ---- Links ----------------------------------------------------------------
    link_service.create_link(
        session, pid, LinkCreate(entity_type="task", entity_id=task_notif.id, url=f"{REPO}/issues/103", title="#103")
    )
    link_service.create_link(
        session, pid, LinkCreate(entity_type="risk", entity_id=risk_unbounded.id, url=f"{REPO}/issues/103", title="#103 tracking issue")
    )
    link_service.create_link(
        session, pid, LinkCreate(entity_type="decision", entity_id=decision_iac.id, url=f"{REPO}/issues/122", title="#122")
    )
    link_service.create_link(
        session, pid, LinkCreate(entity_type="doc", entity_id=doc_audit.id, url=f"{REPO}/issues/111", title="#111 release-readiness audit")
    )

    # ---- Calendar events ------------------------------------------------------
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="Release-readiness review sync",
            status="confirmed",
            start_at="2026-07-28T16:00:00+00:00",
            end_at="2026-07-28T16:30:00+00:00",
            recurrence="weekly",
            phase_id=phases["release"].id,
        ),
    )
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="OSS public launch",
            status="tentative",
            start_at="2026-09-01T00:00:00+00:00",
            all_day=True,
            phase_id=phases["release"].id,
        ),
    )
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="Wave 1 merge freeze",
            status="confirmed",
            start_at="2026-07-25T00:00:00+00:00",
            end_at="2026-07-25T23:59:00+00:00",
            all_day=True,
            phase_id=phases["graph"].id,
        ),
    )

    # ---- Entity connections: one of every relation type ------------------
    entity_connection_service.create_connection(
        session,
        pid,
        EntityConnectionCreate(
            relation_type="depends_on",
            source_entity_type="task",
            source_entity_id=sub_tests.id,
            target_entity_type="task",
            target_entity_id=sub_diff.id,
        ),
    )
    entity_connection_service.create_connection(
        session,
        pid,
        EntityConnectionCreate(
            relation_type="implements",
            source_entity_type="task",
            source_entity_id=task_iac.id,
            target_entity_type="decision",
            target_entity_id=decision_iac.id,
        ),
    )
    entity_connection_service.create_connection(
        session,
        pid,
        EntityConnectionCreate(
            relation_type="mitigates",
            source_entity_type="task",
            source_entity_id=task_notif.id,
            target_entity_type="risk",
            target_entity_id=risk_unbounded.id,
        ),
    )
    entity_connection_service.create_connection(
        session,
        pid,
        EntityConnectionCreate(
            relation_type="contributes_to",
            source_entity_type="task",
            source_entity_id=task_member.id,
            target_entity_type="milestone",
            target_entity_id=mil_wave1.id,
        ),
    )
    entity_connection_service.create_connection(
        session,
        pid,
        EntityConnectionCreate(
            relation_type="references",
            source_entity_type="phase",
            source_entity_id=phases["release"].id,
            target_entity_type="doc",
            target_entity_id=doc_audit.id,
        ),
    )
    entity_connection_service.create_connection(
        session,
        pid,
        EntityConnectionCreate(
            relation_type="related_to",
            source_entity_type="doc",
            source_entity_id=doc_roadmap.id,
            target_entity_type="doc",
            target_entity_id=doc_tour.id,
        ),
    )
    # mil_mvp / doc_canvas / task_shipped are demo content in their own right
    # (achieved milestone, empty canvas doc, custom-status task) — not wired
    # into a connection, so referencing them here would just be noise.
    _ = (mil_mvp, doc_canvas, task_shipped)

    # ---- Agent runs (AI telemetry) -----------------------------------------
    for kwargs in [
        dict(
            agent_family="claude",
            agent_name="Claude Code",
            mode="implement",
            status="succeeded",
            summary="Batched the notification feed and windowed the calendar query in SQL (#103).",
            started_at="2026-07-26T14:00:00+00:00",
            ended_at="2026-07-26T14:42:00+00:00",
        ),
        dict(
            agent_family="claude",
            agent_name="Claude Code",
            mode="review",
            status="succeeded",
            summary="Reviewed the #103 diff for remaining N+1 queries.",
            started_at="2026-07-26T15:00:00+00:00",
            ended_at="2026-07-26T15:14:00+00:00",
        ),
        dict(
            agent_family="codex",
            mode="plan",
            status="succeeded",
            summary="Drafted the release-readiness audit report (#111).",
            started_at="2026-07-24T10:00:00+00:00",
            ended_at="2026-07-24T11:20:00+00:00",
        ),
        dict(
            agent_family="chatgpt",
            mode="summarize",
            status="succeeded",
            summary="Summarized the integration hub phase for the changelog.",
            started_at="2026-07-20T09:00:00+00:00",
            ended_at="2026-07-20T09:18:00+00:00",
        ),
        dict(
            agent_family="cursor",
            mode="debug",
            status="failed",
            summary="Tried to reproduce a flaky LAN-presence test; inconclusive, handed back to a human.",
            started_at="2026-07-22T13:00:00+00:00",
            ended_at="2026-07-22T13:50:00+00:00",
        ),
        dict(
            agent_family="opencode",
            mode="implement",
            status="canceled",
            summary="Started retrofitting the Terraform IaC modules — canceled once #122 decided to retire them instead.",
            started_at="2026-07-23T11:00:00+00:00",
            ended_at="2026-07-23T11:10:00+00:00",
        ),
    ]:
        agent_run_service.create_agent_run(session, pid, AgentRunCreate(**kwargs))

    return project


def main() -> int:
    with Session(engine) as session:
        existing = session.exec(select(Project).where(Project.slug == PROJECT_SLUG)).first()
        if existing is not None:
            print(f"Demo project already seeded (id={existing.id}); nothing to do.")
            return 0
        project = _seed(session)
        project_id = project.id  # read before the session closes (avoids detach)

    print(
        f"Seeded Planarus demo project (id={project_id}). "
        "Open the app's Dashboard and pick 'Planarus Demo — How We Built Planarus'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
