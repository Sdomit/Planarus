"""Seed a Planarus database with the built-in demo project.

This ships with the tool. ``run-planarus.bat`` / ``run-planarus.sh`` call it
with ``--auto`` on every start, right after ``alembic upgrade head``, so a
fresh install opens on a populated cockpit instead of an empty dashboard.

``seed_planarus_project.py`` is the other seed: it loads the real, live
Planarus roadmap (phases + milestones only — that project keeps getting worked
in the app, so it stays minimal on purpose). This one creates a *separate*,
throwaway-safe **"Planarus Demo"** project that exercises the whole feature
surface, so a new user can open one project and see everything the tool does:

    planning graph   phases, stages, tasks, subtasks, checklists, todos
    knowledge        docs of every type, a nested doc tree, @mentions and the
                     backlinks they derive, an Excalidraw canvas with real shapes
    governance       decisions, risks, blockers, milestones, custom statuses
                     for all five entity types
    time             calendar events (all-day, recurring), due dates, milestones
    AI surfaces      pending / applied / rejected approval proposals, agent-run
                     telemetry, an external API key
    operations       notification rules, email log, webhook subscription and
                     its delivery log, the generated on-disk context pack

The content is not Lorem Ipsum: it retells Planarus's own build story (SQLite
→ Postgres, the approval-gated AI surfaces, the #103 unbounded-query fix, the
#122 IaC retirement, the #111 release-readiness audit) using the real phase
names and issue numbers from context/NEXT_STEP.md and CLAUDE.md at the time
this script was written. Treat those as a snapshot, not a live sync.

Dates that a view filters on — task due dates, calendar events, milestone
targets, email log entries — are computed *relative to today* instead of being
hardcoded. A demo seeded a year from now still opens on a calendar with events
in it and a notification bell with something in it.

Idempotent twice over: the ``planarus-demo`` project is only created once, and
a ``demo_seeded`` marker in the ``setting`` table means deleting the demo
project does not resurrect it on the next launch. ``--force`` clears the marker
and re-seeds.

Run against a **migrated** DB (the launchers run ``alembic upgrade head``
first). Honors ``PLANARUS_DATABASE_URL`` / ``DATABASE_URL`` like the rest of
the app.

    cd apps/api && python scripts/seed_demo_project.py           # seed now, loudly
    cd apps/api && python scripts/seed_demo_project.py --auto    # what the launchers run
    cd apps/api && python scripts/seed_demo_project.py --force   # re-seed after deleting it
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core import webhook_crypto
from app.core.config import settings
from app.core.exceptions import ApprovalConflictError, PolicyError
from app.core.utils import new_id, now_utc
from app.db.session import engine
from app.models.email_log import EmailLog
from app.models.project import Project
from app.models.webhook_delivery import WebhookDelivery
from app.models.workspace import Workspace
from app.schemas.agent_run import AgentRunCreate
from app.schemas.api_client import ApiClientCreate
from app.schemas.blocker import BlockerCreate
from app.schemas.calendar_event import CalendarEventCreate
from app.schemas.checklist_item import ChecklistItemCreate
from app.schemas.comment import CommentCreate, CommentUpdate
from app.schemas.decision import DecisionCreate
from app.schemas.doc import DocCreate, DocUpdate
from app.schemas.entity_connection import EntityConnectionCreate
from app.schemas.link import LinkCreate
from app.schemas.milestone import MilestoneCreate
from app.schemas.notifications import NotificationRuleCreate
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
    api_client_service,
    approval_service,
    blocker_service,
    calendar_event_service,
    checklist_service,
    comment_service,
    context_service,
    decision_service,
    doc_service,
    entity_connection_service,
    link_service,
    milestone_service,
    notification_service,
    phase_service,
    project_service,
    risk_service,
    settings_service,
    stage_service,
    status_option_service,
    task_service,
    todo_service,
    webhook_service,
    workspace_service,
)
from sqlmodel import Session, select

WORKSPACE_SLUG = "planarus-demo"
PROJECT_SLUG = "planarus-demo"
REPO = "https://github.com/Sdomit/Planarus"

# Written once the demo has been seeded. Checked *in addition* to the project
# row, so that deleting the demo project in the app is a decision the next
# launch respects rather than undoes. `--force` clears it.
SEEDED_KEY = "demo_seeded"

_NOW = datetime.now(timezone.utc)


def _at(days: float, hour: int = 16) -> str:
    """ISO-8601 UTC timestamp `days` from now, at `hour` o'clock."""
    d = (_NOW + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return d.isoformat()


def _on(days: float) -> str:
    """`YYYY-MM-DD` for a date `days` from now (milestone targets, all-day ends)."""
    return (_NOW + timedelta(days=days)).date().isoformat()


def _demo_folder() -> Optional[str]:
    """An absolute, safe root for the demo project's on-disk context pack.

    The app's own data directory — the same place the Windows launcher already
    writes its logs — so seeding never scatters files through someone's
    Documents. Returns None if it cannot be created, in which case the demo is
    simply folderless and the Context Files view stays empty.
    """
    base = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_DATA_HOME")
        or os.path.join(os.path.expanduser("~"), ".local", "share")
    )
    path = os.path.abspath(os.path.join(base, "Planarus", "demo-project"))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return None
    return path


# `@[Label](task:tsk_123)` in a demo line becomes a real Tiptap mention node,
# which mention_service._extract_targets picks up on save — so the seeded docs
# produce genuine `mention` rows and genuine "Referenced by" backlinks on the
# task/risk/decision/milestone/phase/doc they point at.
_MENTION_RE = re.compile(r"@\[([^\]]+)\]\(([a-z_]+):([^)]+)\)")


def _inline(text: str) -> tuple[list[dict], str]:
    """Split one line into Tiptap inline nodes + its Markdown rendering."""
    nodes: list[dict] = []
    md: list[str] = []
    pos = 0
    for m in _MENTION_RE.finditer(text):
        if m.start() > pos:
            lead = text[pos : m.start()]
            nodes.append({"type": "text", "text": lead})
            md.append(lead)
        label, target_type, target_id = m.group(1), m.group(2), m.group(3)
        nodes.append(
            {
                "type": "mention",
                "attrs": {
                    "targetType": target_type,
                    "targetId": target_id,
                    "label": label,
                },
            }
        )
        # Matches the frontend's Markdown serializer: planarus://<type>/<id>.
        md.append(f"[{label}](planarus://{target_type}/{target_id})")
        pos = m.end()
    if pos < len(text):
        nodes.append({"type": "text", "text": text[pos:]})
        md.append(text[pos:])
    return nodes, "".join(md)


def _tiptap(*lines: str) -> tuple[str, str]:
    """Build (content_json, markdown_cache) for a simple Tiptap doc.

    ``## `` prefixes a heading, ``- `` a single-item bullet list, anything else
    a paragraph. ``@[Label](type:id)`` anywhere becomes a mention. Good enough
    for demo prose; not a Markdown parser.
    """
    nodes: list[dict] = []
    md: list[str] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("## "):
            content, text_md = _inline(line[3:])
            nodes.append({"type": "heading", "attrs": {"level": 2}, "content": content})
            md.append(f"## {text_md}")
        elif line.startswith("- "):
            content, text_md = _inline(line[2:])
            nodes.append(
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [{"type": "paragraph", "content": content}],
                        }
                    ],
                }
            )
            md.append(f"- {text_md}")
        else:
            content, text_md = _inline(line)
            nodes.append({"type": "paragraph", "content": content})
            md.append(text_md)
    return json.dumps({"type": "doc", "content": nodes}), "\n\n".join(md)


# ---- Excalidraw scene builders ---------------------------------------------
# Excalidraw's `restore()` fills in almost every missing field, but `id` and
# `version` must be explicit: CanvasEditor seeds its save-guard from the raw
# parsed elements, so an element without an id gets a random one on load and
# the very first change looks like an edit — an autosave on every open.

_EL_DEFAULTS = {
    "angle": 0,
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 1,
    "opacity": 100,
    "groupIds": [],
    "frameId": None,
    "roundness": None,
    "version": 1,
    "isDeleted": False,
    "boundElements": [],
    "link": None,
    "locked": False,
}


def _el(**over) -> dict:
    el = dict(_EL_DEFAULTS)
    el.update(over)
    el.setdefault("versionNonce", abs(hash(el["id"])) % 2_000_000_000)
    el.setdefault("seed", abs(hash(el["id"] + "s")) % 2_000_000_000)
    return el


def _card(idx: int, x: int, y: int, kind: str, entity_id: str, text: str) -> list[dict]:
    """A Planarus entity card: a rounded rectangle with a bound text label.

    `customData.planarusEntity` is what makes the card click through to the
    entity in the app rather than being an anonymous rectangle.
    """
    palette = {
        "task": ("#e8f0fe", "#3b6fb0"),
        "risk": ("#fdeceb", "#c0483f"),
        "decision": ("#e9f6ec", "#3f8a4f"),
        "milestone": ("#fff3e0", "#c07f2a"),
    }
    bg, stroke = palette.get(kind, ("#f1f5f9", "#64748b"))
    box_id = f"demo-card-{idx}"
    label_id = f"demo-card-{idx}-label"
    return [
        _el(
            id=box_id,
            type="rectangle",
            x=x,
            y=y,
            width=240,
            height=100,
            index=f"a{idx * 2}",
            strokeColor=stroke,
            backgroundColor=bg,
            roundness={"type": 3},
            boundElements=[{"type": "text", "id": label_id}],
            customData={"planarusEntity": {"kind": kind, "id": entity_id}},
        ),
        _el(
            id=label_id,
            type="text",
            x=x + 12,
            y=y + 26,
            width=216,
            height=48,
            index=f"a{idx * 2 + 1}",
            strokeColor="#1e1e1e",
            backgroundColor="transparent",
            text=text,
            originalText=text,
            fontSize=16,
            fontFamily=5,
            textAlign="center",
            verticalAlign="middle",
            containerId=box_id,
            autoResize=True,
            lineHeight=1.25,
        ),
    ]


def _arrow(idx: int, x: int, y: int, width: int) -> dict:
    return _el(
        id=f"demo-arrow-{idx}",
        type="arrow",
        x=x,
        y=y,
        width=width,
        height=0,
        index=f"z{idx}",
        strokeColor="#1e1e1e",
        backgroundColor="transparent",
        roundness={"type": 2},
        points=[[0, 0], [width, 0]],
        lastCommittedPoint=None,
        startBinding=None,
        endBinding=None,
        startArrowhead=None,
        endArrowhead="arrow",
        elbowed=False,
    )


def _scene(elements: list[dict]) -> str:
    return json.dumps(
        {
            "type": "excalidraw",
            "version": 2,
            "source": "planarus",
            "elements": elements,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }
    )


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

    base = ProjectCreate(
        workspace_id=ws.id,
        title="Planarus Demo — How We Built Planarus",
        slug=PROJECT_SLUG,
        summary=(
            "A tour of every Planarus feature, told through Planarus's own build "
            "history: phases, tasks, docs, risks, decisions, approvals, and the "
            "real fixes behind issues #103, #111, #119 and #122."
        ),
        status="active",
        priority="high",
    )
    # A folder_path is what makes the Context Files and Preview views real:
    # create_project provisions the folder and generates the context/*.md pack
    # off the back of it. If the path is refused (another project already owns
    # it, say), fall back to a folderless demo rather than seeding nothing.
    folder = _demo_folder()
    try:
        project = project_service.create_project(
            session, base.model_copy(update={"folder_path": folder})
        )
    except PolicyError as exc:
        print(f"  demo folder refused ({exc}); seeding without an on-disk pack.")
        folder = None
        project = project_service.create_project(session, base)
    pid = project.id

    # ---- Custom statuses: one per entity type that supports them -----------
    # Created before anything that uses them — the services validate an entity's
    # status against the built-ins *plus* whatever custom options exist.
    for entity_type, label, category, color in [
        ("task", "Shipped \U0001f680", "done", "#22c55e"),
        ("task", "In QA", "open", "#f59e0b"),
        ("phase", "Frozen", "open", "#64748b"),
        ("risk", "Escalated", "open", "#ef4444"),
        ("milestone", "At Risk", "open", "#f97316"),
        ("decision", "Under Review", "open", "#3b82f6"),
    ]:
        status_option_service.create_status_option(
            session,
            pid,
            StatusOptionCreate(
                entity_type=entity_type, label=label, category=category, color=color
            ),
        )

    # ---- Phases (condensed real arc) --------------------------------------
    phases = {}
    for key, title, status in [
        ("foundation", "Phase 1-2 — Foundation: runnable app + SQLite", "done"),
        ("core", "Phase 4-7 — Planning core: phases, tasks, docs, approvals", "done"),
        ("ai", "Phase 7B-7C — AI surfaces: MCP + external API, approval-gated", "done"),
        ("team", "Phase 10-11 — Team & hosted groundwork: LAN mode, admin, integrations", "done"),
        ("graph", "Phase 15-19 — Planning graph: boards, roadmap, calendar, connections", "active"),
        ("release", "Release readiness — audit, IaC cleanup, public launch", "blocked"),
        ("hosted", "Phase 14 — Hosted / SaaS mode", "frozen"),
    ]:
        phases[key] = phase_service.create_phase(
            session, pid, PhaseCreate(title=title, status=status)
        )

    # ---- Stages -------------------------------------------------------------
    stages = {}
    for key, phase_key, title, status in [
        ("statuses", "graph", "Custom statuses & board columns (#88)", "done"),
        ("connections", "graph", "Entity connections & dependency graph (#94)", "active"),
        ("calsync", "graph", "Calendar sync (Google / Microsoft)", "planned"),
        ("editor", "core", "Notion-style document editor", "done"),
        ("approvals", "core", "Approval queue & audit trail", "done"),
    ]:
        stages[key] = stage_service.create_stage(
            session,
            pid,
            StageCreate(phase_id=phases[phase_key].id, title=title, status=status),
        )

    # ---- Tasks: statuses, priorities, subtasks, due dates, custom status ---
    # Every phase and stage carries at least one task: the Roadmap rolls
    # completion up from them, and a phase with none reads as 0% forever.
    for title, status, priority, phase_key, stage_key in [
        ("Stand up the FastAPI + SQLModel skeleton", "done", "high", "foundation", None),
        ("Wire Alembic migrations end to end", "done", "high", "foundation", None),
        ("Build the phase / stage / task hierarchy", "done", "high", "core", None),
        ("Ship the Notion-style document editor", "done", "high", "core", "editor"),
        ("Build the approval queue and audit trail", "done", "urgent", "core", "approvals"),
        ("Add slash-menu tables to the editor", "done", "med", "core", "editor"),
    ]:
        task_service.create_task(
            session,
            pid,
            TaskCreate(
                title=title,
                status=status,
                priority=priority,
                phase_id=phases[phase_key].id,
                stage_id=stages[stage_key].id if stage_key else None,
            ),
        )

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
    # Overdue on purpose: this is what lights up the notifications bell and the
    # "Needs attention" strip the moment the demo is opened.
    task_ghsupport = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="File GitHub Support ticket to purge stale pull refs (#119)",
            description="99 of 108 server-side refs/pull/* still reach the pre-rewrite history. Only a support-side purge removes them.",
            status="blocked",
            priority="urgent",
            phase_id=phases["release"].id,
            due_at=_at(-4, hour=17),
        ),
    )
    task_audit = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Draft release-readiness audit report (#111)",
            status="needs_review",
            priority="med",
            phase_id=phases["release"].id,
            due_at=_at(2, hour=17),
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
    task_connections = task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Ship the entity connection graph (#94)",
            description="depends_on / implements / mitigates / contributes_to / references / related_to, with cycle detection.",
            status="in_qa",
            priority="high",
            phase_id=phases["graph"].id,
            stage_id=stages["connections"].id,
            due_at=_at(5, hour=17),
        ),
    )
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Plan Phase 14 hosted/SaaS mode",
            status="ready",
            priority="low",
            phase_id=phases["hosted"].id,
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
            phase_id=phases["hosted"].id,
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
    # Stale on purpose: in_progress with no movement for longer than the
    # 10-day threshold, which is the other half of "Needs attention".
    task_service.create_task(
        session,
        pid,
        TaskCreate(
            title="Document the LAN team-mode setup path",
            description="Started, then parked behind release readiness.",
            status="in_progress",
            priority="low",
            phase_id=phases["team"].id,
        ),
    )

    # ---- Checklist items ----------------------------------------------------
    for label, done in [
        ("Define STATUS_CATEGORIES enum", True),
        ("Add status_option table + service", True),
        ("Wire board columns to custom statuses", True),
    ]:
        checklist_service.create_checklist_item(
            session, task_customstatus.id, ChecklistItemCreate(label=label, done=done)
        )
    for label, done in [
        ("Cycle detection on depends_on", True),
        ("Canonical uniqueness index", True),
        ("Connection panel on every entity", False),
        ("Backfill test for the 6 relation types", False),
    ]:
        checklist_service.create_checklist_item(
            session, task_connections.id, ChecklistItemCreate(label=label, done=done)
        )

    # ---- Blockers -----------------------------------------------------------
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
    blocker_service.create_blocker(
        session,
        pid,
        BlockerCreate(
            title="Postgres CI job had no driver installed",
            description="Resolved by adding the [postgres] extra to the dialect job.",
            status="resolved",
        ),
    )

    # ---- Milestones ---------------------------------------------------------
    mil_mvp = milestone_service.create_milestone(
        session, pid, MilestoneCreate(title="MVP + V1 feature-complete", status="achieved")
    )
    mil_wave1 = milestone_service.create_milestone(
        session,
        pid,
        MilestoneCreate(
            title="Release-readiness Wave 1 closed",
            status="achieved",
            phase_id=phases["release"].id,
        ),
    )
    mil_launch = milestone_service.create_milestone(
        session,
        pid,
        MilestoneCreate(
            title="OSS public launch",
            status="active",
            phase_id=phases["release"].id,
            target_date=_on(21),
        ),
    )
    milestone_service.create_milestone(
        session,
        pid,
        MilestoneCreate(
            title="Hosted SaaS beta",
            status="at_risk",
            phase_id=phases["hosted"].id,
            target_date=_on(75),
        ),
    )
    milestone_service.create_milestone(
        session,
        pid,
        MilestoneCreate(
            title="Public docs site live",
            status="planned",
            phase_id=phases["release"].id,
            target_date=_on(9),
        ),
    )

    # ---- Risks --------------------------------------------------------------
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
    risk_replica = risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="A second API replica would split local state",
            description="Rate-limit buckets, the local control token, and LAN presence are process-local.",
            severity="critical",
            status="accepted",
            mitigation="Hosted runtime contract: one process, one replica, autoscaling off — enforced by create_app() and scripts/doctor.py.",
            phase_id=phases["hosted"].id,
        ),
    )
    risk_refs = risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="Stale GitHub pull refs block public visibility (#119)",
            description="99 of 108 server-side refs/pull/* still reach the pre-rewrite commit.",
            severity="medium",
            status="escalated",
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
    risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="An agent could quietly rewrite the plan",
            description="The whole reason writes from MCP and the external API are proposals, never commits.",
            severity="low",
            status="monitoring",
            mitigation="Approval queue: every AI write is a diff a human approves or rejects.",
            phase_id=phases["ai"].id,
        ),
    )
    # Left in the `open` state on purpose: the dashboard's "Open risks" tile
    # counts that status literally, so a register where everything has already
    # been triaged makes the tile read zero on a project that clearly has risks.
    risk_service.create_risk(
        session,
        pid,
        RiskCreate(
            title="No load testing has been done above a single user",
            description="Local-first means one writer, but LAN team mode puts several people on one SQLite file.",
            severity="medium",
            status="open",
            phase_id=phases["team"].id,
        ),
    )

    # ---- Decisions ----------------------------------------------------------
    decision_sqlite = decision_service.create_decision(
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
    decision_approval = decision_service.create_decision(
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
            phase_id=phases["hosted"].id,
        ),
    )
    decision_service.create_decision(
        session,
        pid,
        DecisionCreate(
            title="Ship the browser extension as select-to-capture only",
            context="A full in-page editor is a second frontend to maintain.",
            decision="Clip the selection into a task/decision/risk/todo/doc and stop there.",
            status="under_review",
            phase_id=phases["team"].id,
        ),
    )
    decision_service.create_decision(
        session,
        pid,
        DecisionCreate(
            title="Store documents as Tiptap JSON, export Markdown",
            context="Markdown-as-source loses block identity; JSON-as-source is unreadable on disk.",
            decision="content_json is canonical, markdown_cache is derived, the disk export is a snapshot.",
            status="superseded",
            phase_id=phases["core"].id,
        ),
    )

    # ---- Docs: every type, a nested tree, colors, and real @mentions --------
    doc_tour = doc_service.create_doc(
        session,
        pid,
        DocCreate(
            title="Demo tour — how to use this project",
            doc_type="note",
            status="published",
            color="yellow",
        ),
    )
    content, md = _tiptap(
        "## Start here",
        "This project is a live tour of Planarus, seeded with the real story of how Planarus itself got built. Nothing here is Lorem Ipsum.",
        "- Roadmap: the phases and stages, with completion rolled up from statuses",
        "- Planning: the task board, with custom columns like \"Shipped\" and \"In QA\" alongside the built-ins",
        "- Approvals: proposals an AI agent made, waiting for you to approve or reject",
        "- Docs: this editor, with @mentions that create real backlinks",
        "- Canvas: an Excalidraw whiteboard whose cards link back to entities",
        "- Calendar, Timeline, Context Pack, Agent Runs, Reminders: all populated",
        f"The current frontier is @[OSS public launch](milestone:{mil_launch.id}), gated on @[File GitHub Support ticket to purge stale pull refs (#119)](task:{task_ghsupport.id}).",
        "Everything here is disposable — delete the 'planarus-demo' project any time, then re-run scripts/seed_demo_project.py --force to bring it back.",
    )
    doc_service.update_doc(
        session, doc_tour.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    doc_roadmap = doc_service.create_doc(
        session,
        pid,
        DocCreate(title="Roadmap overview", doc_type="plan", status="published", color="blue"),
    )
    content, md = _tiptap(
        "## Roadmap overview",
        "Planarus shipped in phases: a runnable foundation, then the planning core (phases/tasks/docs/approvals), then approval-gated AI surfaces (MCP + external API), then team and hosted groundwork, then the planning graph (boards, roadmap, calendar, connections).",
        "Release readiness is the current frontier: an audit returned NO-GO pending two waves of fixes, most of which are closed.",
        f"The one remaining blocker is tracked as @[Stale GitHub pull refs block public visibility (#119)](risk:{risk_refs.id}).",
        f"Hosted mode is deliberately frozen behind @[A second API replica would split local state](risk:{risk_replica.id}).",
    )
    doc_service.update_doc(
        session, doc_roadmap.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    # Nested under the roadmap — the doc tree is a real tree, not a flat list.
    doc_spec = doc_service.create_doc(
        session,
        pid,
        DocCreate(
            title="Approval engine contract",
            doc_type="spec",
            status="published",
            parent_doc_id=doc_roadmap.id,
            color="green",
        ),
    )
    content, md = _tiptap(
        "## Approval engine contract",
        "Every write proposed through an external AI surface (MCP, the HTTP API) is approval-gated: preview, then a human approves, then it commits.",
        "- ApprovalRequest carries a risk_level, a policy_version, and a checksum-bound diff",
        "- A proposal whose target moved since it was made is invalidated, not silently applied",
        "- Expired or invalidated requests cannot be applied",
        "- Applying writes an audit event, always",
        f"This implements @[All AI-surface writes are approval-gated](decision:{decision_approval.id}).",
    )
    doc_service.update_doc(
        session, doc_spec.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    doc_research = doc_service.create_doc(
        session,
        pid,
        DocCreate(
            title="Why SQLite -> Postgres, not just Postgres",
            doc_type="research",
            status="published",
            parent_doc_id=doc_roadmap.id,
        ),
    )
    content, md = _tiptap(
        "## Why SQLite, then Postgres — not just Postgres",
        "Local-first means the app has to run with zero install. SQLite gives that for free.",
        "Hosted/LAN mode needs real concurrent writers, so the same schema targets Postgres there.",
        "One SQLModel layer, two engines, Alembic migrations that run against either.",
        f"Recorded as @[Use SQLite for local mode, Postgres for hosted/LAN](decision:{decision_sqlite.id}).",
    )
    doc_service.update_doc(
        session, doc_research.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    doc_audit = doc_service.create_doc(
        session,
        pid,
        DocCreate(
            title="Release-readiness audit findings (#111)",
            doc_type="reference",
            status="published",
            color="red",
        ),
    )
    content, md = _tiptap(
        "## Release-readiness audit findings (#111)",
        "The audit returned NO-GO — keep the repo private until the release blockers close.",
        "Wave 0 closed: #86, #87, #88, #89, #113, #114, #115, and the #119 history rewrite executed.",
        "Wave 1 closed: #124, #116, #117, #118, #120, #122.",
        "#119 stays open on one thing only: a GitHub Support purge of stale server-side pull refs.",
        f"Write-up owner: @[Draft release-readiness audit report (#111)](task:{task_audit.id}). Phase: @[Release readiness — audit, IaC cleanup, public launch](phase:{phases['release'].id}).",
    )
    doc_service.update_doc(
        session, doc_audit.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    # A draft, so the docs list shows both states.
    doc_draft = doc_service.create_doc(
        session,
        pid,
        DocCreate(title="Launch announcement (draft)", doc_type="other", status="draft", color="purple"),
    )
    content, md = _tiptap(
        "## Launch post — working draft",
        "Planarus is a local-first project cockpit. Your AI agents propose; you approve.",
        "Still to do: pick the screenshots, decide whether the hosted beta gets a mention.",
    )
    doc_service.update_doc(
        session, doc_draft.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    # A quick note — the Notes view is this same engine filtered to note cards.
    doc_note = doc_service.create_doc(
        session,
        pid,
        DocCreate(title="Scratch: launch-day checklist", doc_type="note", status="draft", color="teal"),
    )
    content, md = _tiptap(
        "- Flip repository visibility to public",
        "- Publish the release tag and changelog",
        "- Post the launch thread",
        "- Watch the issue tracker for the first hour",
    )
    doc_service.update_doc(
        session, doc_note.id, DocUpdate(version=1, content_json=content, markdown_cache=md)
    )

    # ---- Canvas: a real Excalidraw scene, cards bound to real entities ------
    doc_canvas = doc_service.create_doc(
        session,
        pid,
        DocCreate(
            title="Architecture sketch",
            doc_type="canvas",
            editor_format="excalidraw",
            status="draft",
        ),
    )
    elements: list[dict] = []
    elements += _card(
        0, 80, 100, "task", mcp_parent.id,
        "✔ Task\nShip the approval-gated MCP server\nin_progress · high",
    )
    elements += _card(
        1, 420, 100, "decision", decision_approval.id,
        "⚖ Decision\nAll AI-surface writes are approval-gated\naccepted",
    )
    elements += _card(
        2, 760, 100, "risk", risk_replica.id,
        "⚠ Risk\nA second API replica would split local state\ncritical · accepted",
    )
    elements += _card(
        3, 420, 300, "milestone", mil_launch.id,
        "◆ Milestone\nOSS public launch\nactive",
    )
    elements.append(_arrow(0, 328, 150, 84))
    elements.append(_arrow(1, 668, 150, 84))
    doc_service.update_doc(
        session,
        doc_canvas.id,
        DocUpdate(version=1, content_json=_scene(elements), markdown_cache=""),
    )

    # ---- Comments: all three author types and all three triage states ------
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
    cmt_attention = comment_service.create_comment(
        session,
        pid,
        CommentCreate(
            entity_type="decision",
            entity_id=decision_iac.id,
            body="Confirmed: no cloud-init script ever wrote PLANARUS_OAUTH_REDIRECT_URIS — that's the case for deleting rather than patching.",
            author_type="agent",
        ),
    )
    comment_service.update_comment(
        session, cmt_attention.id, CommentUpdate(status="attention")
    )
    cmt_done = comment_service.create_comment(
        session,
        pid,
        CommentCreate(
            entity_type="risk",
            entity_id=risk_unbounded.id,
            body="Re-ran the feed benchmark after batching: flat to 10k rows.",
            author_type="human",
        ),
    )
    comment_service.update_comment(session, cmt_done.id, CommentUpdate(status="done"))
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
    comment_service.create_comment(
        session,
        pid,
        CommentCreate(
            entity_type="milestone",
            entity_id=mil_launch.id,
            body="Launch date moves with the #119 support ticket, not with code.",
            author_type="system",
        ),
    )

    # ---- Todos (nested scratch list) ---------------------------------------
    todo_record = todo_service.create_todo(
        session, pid, TodoCreate(label="Record a 2-minute demo video")
    )
    todo_service.create_todo(
        session, pid, TodoCreate(label="Script the walkthrough", parent_id=todo_record.id, done=True)
    )
    todo_capture = todo_service.create_todo(
        session, pid, TodoCreate(label="Capture screen recording", parent_id=todo_record.id)
    )
    todo_service.create_todo(
        session, pid, TodoCreate(label="Trim and add captions", parent_id=todo_capture.id)
    )
    todo_service.create_todo(
        session, pid, TodoCreate(label="Share the demo project link with the team")
    )

    # ---- Links --------------------------------------------------------------
    for entity_type, entity_id, num, title in [
        ("task", task_notif.id, 103, "#103"),
        ("risk", risk_unbounded.id, 103, "#103 tracking issue"),
        ("decision", decision_iac.id, 122, "#122"),
        ("doc", doc_audit.id, 111, "#111 release-readiness audit"),
        ("task", task_ghsupport.id, 119, "#119 stale pull refs"),
        ("milestone", mil_launch.id, 111, "#111 launch gate"),
    ]:
        link_service.create_link(
            session,
            pid,
            LinkCreate(
                entity_type=entity_type,
                entity_id=entity_id,
                url=f"{REPO}/issues/{num}",
                title=title,
            ),
        )

    # ---- Calendar events (relative, so the current month is never empty) ----
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="Release-readiness review sync",
            description="Standing 30 minutes on the open release blockers.",
            location="Video call",
            status="confirmed",
            start_at=_at(1, hour=16),
            end_at=_at(1, hour=17),
            recurrence="weekly",
            recurrence_until=_on(60),
            phase_id=phases["release"].id,
        ),
    )
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="OSS public launch",
            status="tentative",
            start_at=_on(21),
            all_day=True,
            phase_id=phases["release"].id,
        ),
    )
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="Merge freeze",
            status="confirmed",
            start_at=_on(14),
            end_at=_on(16),
            all_day=True,
            phase_id=phases["graph"].id,
        ),
    )
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="Daily standup",
            status="confirmed",
            start_at=_at(0, hour=9),
            end_at=_at(0, hour=9),
            recurrence="daily",
            # Short run on purpose: daily recurrence needs demonstrating, but a
            # month of it buries every other event in the month view.
            recurrence_until=_on(9),
        ),
    )
    calendar_event_service.create_calendar_event(
        session,
        pid,
        CalendarEventCreate(
            title="Monthly roadmap review",
            status="confirmed",
            start_at=_at(7, hour=14),
            end_at=_at(7, hour=15),
            recurrence="monthly",
        ),
    )

    # ---- Entity connections: one of every relation type --------------------
    for relation, s_type, s_id, t_type, t_id in [
        ("depends_on", "task", sub_tests.id, "task", sub_diff.id),
        ("implements", "task", task_iac.id, "decision", decision_iac.id),
        ("mitigates", "task", task_notif.id, "risk", risk_unbounded.id),
        ("contributes_to", "task", task_member.id, "milestone", mil_wave1.id),
        ("references", "phase", phases["release"].id, "doc", doc_audit.id),
        ("related_to", "doc", doc_roadmap.id, "doc", doc_tour.id),
        # Directions are validated: depends_on is task->task, implements is
        # task->decision, contributes_to is task->milestone, references is
        # <planning entity>->doc. related_to is the only free-form one.
        ("contributes_to", "task", task_connections.id, "milestone", mil_launch.id),
        ("references", "task", task_audit.id, "doc", doc_audit.id),
        ("related_to", "risk", risk_refs.id, "milestone", mil_launch.id),
    ]:
        entity_connection_service.create_connection(
            session,
            pid,
            EntityConnectionCreate(
                relation_type=relation,
                source_entity_type=s_type,
                source_entity_id=s_id,
                target_entity_type=t_type,
                target_entity_id=t_id,
            ),
        )
    # mil_mvp and task_shipped are demo content in their own right (an achieved
    # milestone, a custom-status task) — not wired into a connection, so
    # referencing them here would just be noise.
    _ = (mil_mvp, task_shipped, doc_note, doc_draft)

    # ---- Agent runs (AI telemetry + analytics) ------------------------------
    for kwargs in [
        dict(
            agent_family="claude",
            agent_name="Claude Code",
            mode="implement",
            status="succeeded",
            summary="Batched the notification feed and windowed the calendar query in SQL (#103).",
            started_at=_at(-1, hour=14),
            ended_at=_at(-1, hour=15),
        ),
        dict(
            agent_family="claude",
            agent_name="Claude Code",
            mode="review",
            status="succeeded",
            summary="Reviewed the #103 diff for remaining N+1 queries.",
            started_at=_at(-1, hour=16),
            ended_at=_at(-1, hour=17),
        ),
        dict(
            agent_family="codex",
            agent_name="Codex CLI",
            mode="plan",
            status="succeeded",
            summary="Drafted the release-readiness audit report (#111).",
            started_at=_at(-3, hour=10),
            ended_at=_at(-3, hour=11),
        ),
        dict(
            agent_family="chatgpt",
            agent_name="Custom GPT (Actions)",
            mode="summarize",
            status="succeeded",
            summary="Summarized the integration hub phase for the changelog.",
            started_at=_at(-7, hour=9),
            ended_at=_at(-7, hour=10),
        ),
        dict(
            agent_family="cursor",
            mode="debug",
            status="failed",
            summary="Tried to reproduce a flaky LAN-presence test; inconclusive, handed back to a human.",
            started_at=_at(-5, hour=13),
            ended_at=_at(-5, hour=14),
        ),
        dict(
            agent_family="opencode",
            mode="implement",
            status="canceled",
            summary="Started retrofitting the Terraform IaC modules — canceled once #122 decided to retire them instead.",
            started_at=_at(-4, hour=11),
            ended_at=_at(-4, hour=12),
        ),
        dict(
            agent_family="claude",
            agent_name="Claude Desktop (MCP)",
            mode="plan",
            status="started",
            summary="Reading the context pack ahead of the launch checklist.",
            started_at=_at(0, hour=9),
        ),
    ]:
        agent_run_service.create_agent_run(session, pid, AgentRunCreate(**kwargs))

    # ---- Email reminders: a rule plus a send history ------------------------
    rule = notification_service.create_rule(
        session,
        pid,
        NotificationRuleCreate(
            channel="email",
            trigger_type="due_soon",
            enabled=True,
            to_email="you@example.com",
            threshold_hours=48,
        ),
    )
    notification_service.create_rule(
        session,
        pid,
        NotificationRuleCreate(
            channel="email",
            trigger_type="daily_digest",
            enabled=False,
            to_email="you@example.com",
            threshold_hours=24,
        ),
    )
    # No public creator for the log — the real path needs a live SMTP server —
    # so mirror what email_service._log writes. Dated in the past so the seeded
    # history does not eat into today's send cap.
    for days, subject, status, error in [
        (-1, "[Planarus] Planarus Demo — 2 tasks due soon", "sent", None),
        (-2, "[Planarus] Planarus Demo — 1 task due soon", "sent", None),
        (
            -3,
            "[Planarus] Planarus Demo — 3 tasks due soon",
            "failed",
            "ConnectionRefusedError: no SMTP server on 127.0.0.1:1025",
        ),
    ]:
        session.add(
            EmailLog(
                id=new_id("eml"),
                project_id=pid,
                rule_id=rule.id,
                to_email=rule.to_email,
                subject=subject,
                status=status,
                error=error,
                sent_at=_at(days, hour=8),
                created_at=now_utc(),
            )
        )
    session.commit()

    # ---- External API key ---------------------------------------------------
    # The raw key is shown once and is unrecoverable by design; the demo only
    # needs the row so the Settings > API keys panel is not empty.
    api_client_service.create_client(
        session,
        ApiClientCreate(
            label="Demo read-only key (custom GPT)",
            workspace_id=ws.id,
            project_ids=[pid],
            can_read=True,
            can_propose=False,
            expires_in_days=90,
        ),
    )
    api_client_service.create_client(
        session,
        ApiClientCreate(
            label="Demo propose key (MCP agent)",
            workspace_id=ws.id,
            project_ids=[pid],
            can_read=True,
            can_propose=True,
            expires_in_days=90,
        ),
    )

    # ---- Approvals: the flagship surface ------------------------------------
    # Deliberately last among the mutations. A proposal is checksum-bound to its
    # target's state at proposal time, so editing a target afterwards would
    # invalidate the proposal — which is the feature working, but a poor demo.
    approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="task.create",
        patch={
            "title": "Add a queue-depth metric to the Cockpit",
            "description": "Proposed by an agent while reviewing the #103 fix: the fix removed the N+1, but nothing surfaces backlog depth.",
            "status": "backlog",
            "priority": "med",
            "phase_id": phases["graph"].id,
        },
        actor_ref="claude-desktop",
        origin="mcp",
    )
    approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="task.update",
        target_entity_id=task_audit.id,
        patch={"status": "in_progress", "priority": "high"},
        actor_ref="custom-gpt",
        origin="api",
    )
    approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="connection.create",
        patch={
            "relation_type": "mitigates",
            "source_entity_type": "task",
            "source_entity_id": task_connections.id,
            "target_entity_type": "risk",
            "target_entity_id": risk_refs.id,
        },
        actor_ref="claude-desktop",
        origin="mcp",
    )

    # One approved-and-applied, so the audit trail and the history tab have
    # something real in them. The decision it creates is a genuine row.
    applied = approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="decision.create",
        patch={
            "title": "Ship webhooks behind an env-gated encryption key",
            "context": "A webhook signing secret is a recoverable credential; storing it in plaintext is not an option.",
            "decision": "Require an encryption key at rest; the feature stays inert until one is configured.",
            "status": "accepted",
        },
        actor_ref="claude-desktop",
        origin="mcp",
    )
    # An expired or fingerprint-shifted proposal refuses to apply — correct
    # behaviour, but it must not take the whole seed down with it.
    try:
        approval_service.approve(session, applied.id)
        approval_service.apply(session, applied.id)
    except ApprovalConflictError as exc:
        print(f"  applied-approval demo skipped: {exc}")

    rejected = approval_service.create_proposal(
        session,
        project_id=pid,
        action_type="task.create",
        patch={
            "title": "Rewrite the storage layer in Rust",
            "description": "Suggested by an agent asked to improve write throughput.",
            "status": "backlog",
            "priority": "low",
        },
        actor_ref="custom-gpt",
        origin="api",
    )
    try:
        approval_service.reject(
            session,
            rejected.id,
            reason="Out of scope. SQLite is not the bottleneck, and this is exactly the kind of change the approval gate exists to stop.",
        )
    except ApprovalConflictError as exc:
        print(f"  rejected-approval demo skipped: {exc}")

    # ---- Webhooks (only when the signing key is configured) ----------------
    # Without PLANARUS_WEBHOOK_ENC_KEY the whole feature is inert and the
    # Settings card says so, so there is nothing for a seeded row to show.
    #
    # Last on purpose, and seeded disabled. webhook_service installs commit
    # listeners on every session: an enabled subscription created earlier would
    # POST every entity this script goes on to create — and every edit the user
    # later makes in the demo — to a URL they never chose. A demo must not
    # generate real outbound traffic. The row is here to be looked at; flipping
    # it on is the user's decision.
    if webhook_crypto.is_enabled():
        try:
            sub, _secret = webhook_service.create_subscription(
                session,
                workspace_id=ws.id,
                target_url="https://example.com/planarus-demo-hook",
                event_kinds=["task.create", "decision.create"],
                project_ids=[pid],
                fmt="json",
            )
            sub.enabled = False
            session.add(sub)
            for kind, status, code, error in [
                ("task.create", "delivered", 200, None),
                ("decision.create", "delivered", 200, None),
                ("task.create", "failed", 502, "upstream returned 502"),
            ]:
                session.add(
                    WebhookDelivery(
                        id=new_id("whd"),
                        subscription_id=sub.id,
                        event_kind=kind,
                        request_body=json.dumps({"kind": kind, "project_id": pid}),
                        status=status,
                        status_code=code,
                        error=error,
                        attempt=1,
                        created_at=now_utc(),
                        delivered_at=now_utc() if status == "delivered" else None,
                    )
                )
            session.commit()
        except (RuntimeError, ImportError, ValueError) as exc:
            print(f"  skipping the webhook demo: {exc}")

    # ---- Context pack on disk ----------------------------------------------
    # create_project already provisioned it; regenerate now that the project has
    # content, so context/*.md reflects the finished demo rather than an empty
    # shell. Non-fatal: a demo without the on-disk pack is still a demo.
    if folder:
        try:
            context_service.provision_and_regenerate(session, project)
        except Exception as exc:  # noqa: BLE001 — never fail the seed over disk
            print(f"  context pack regeneration skipped: {exc}")

    return project


def _already_seeded(session: Session) -> Optional[str]:
    """Why the seed should not run, or None if it should."""
    existing = session.exec(
        select(Project).where(Project.slug == PROJECT_SLUG)
    ).first()
    if existing is not None:
        return f"demo project already present (id={existing.id})"
    if settings_service.get_setting(session, SEEDED_KEY, False):
        return "demo was seeded before and has since been deleted"
    return None


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the built-in Planarus demo project."
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help=(
            "Launcher mode: skip in team/hosted mode, honour PLANARUS_SEED_DEMO=0, "
            "and never fail the process — a demo is not worth blocking a boot for."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if the demo was seeded and deleted before.",
    )
    args = parser.parse_args(argv)

    if args.auto:
        if os.environ.get("PLANARUS_SEED_DEMO", "").strip().lower() in {"0", "false", "no"}:
            return 0
        # Auth-enabled deployments bootstrap through an admin claiming a
        # workspace. Dropping a pre-owned demo project into that flow is a
        # support ticket waiting to happen; hosted operators run this by hand.
        if settings.auth_enabled:
            return 0

    try:
        with Session(engine) as session:
            if args.force:
                settings_service.set_setting(session, SEEDED_KEY, False)
                session.commit()
            skip = _already_seeded(session)
            if skip is not None:
                if not args.auto:
                    print(f"Nothing to do: {skip}.")
                return 0
            project = _seed(session)
            project_id = project.id  # read before the session closes (avoids detach)
            settings_service.set_setting(session, SEEDED_KEY, True)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        if args.auto:
            # The app is the product; the demo is a welcome mat. Never let a
            # failed welcome mat stop the server from starting.
            print(f"[demo seed] skipped: {exc}", file=sys.stderr)
            return 0
        raise

    print(
        f"Seeded the Planarus demo project (id={project_id}). "
        "Open the Dashboard and pick 'Planarus Demo — How We Built Planarus'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
