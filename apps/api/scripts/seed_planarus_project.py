"""Seed a running Planarus database with the Planarus project itself (dogfooding).

Planarus manages Planarus: this loads the real roadmap — every phase plus the
launch milestones — into a running DB so you can follow progress in the app's
Roadmap / Task Board instead of only the Markdown context pack. Phase and
milestone titles + statuses mirror context/NEXT_STEP.md; slice-level detail
lives in docs/dev/ and docs/plan/, not here.

Idempotent at the project level: if the ``planarus`` project already exists it
does nothing (re-running is safe). Run against a **migrated** DB — the app applies
migrations on startup, or run ``alembic upgrade head`` first. Honors
``PLANARUS_DATABASE_URL`` / ``DATABASE_URL`` like the rest of the app.

    cd apps/api && python scripts/seed_planarus_project.py
"""
import sys

from app.db.session import engine
from app.models.project import Project
from app.models.workspace import Workspace
from app.schemas.milestone import MilestoneCreate
from app.schemas.phase import PhaseCreate
from app.schemas.project import ProjectCreate
from app.schemas.workspace import WorkspaceCreate
from app.services import (
    milestone_service,
    phase_service,
    project_service,
    workspace_service,
)
from sqlmodel import Session, select

WORKSPACE_SLUG = "planarus"
PROJECT_SLUG = "planarus"
# Pre-rename slugs (AgentBoard → Approvo → Planarus), OLDEST LAST. These are live
# DB values, not brand references — a DB seeded before a rename still carries the
# old slug, so both lookups below match these too and re-seeding stays a no-op
# instead of creating a duplicate workspace/project. Do not "clean up" to the
# current name.
LEGACY_SLUGS = ("approvo", "agentboard")

# (title, status). Phases 0–18 shipped; 7C2b and 14 remain planned/deferred.
# Flat phases mirror the live roadmap; per-slice tasks are worked in the app.
PHASES: list[dict] = [
    {"title": "Phase 0 — Documentation acceptance gate", "status": "done"},
    {"title": "Phase 1 — Minimal runnable foundation", "status": "done"},
    {"title": "Phase 2 — SQLite + project CRUD", "status": "done"},
    {"title": "Phase 3 — Project folder + Markdown generation (fs-memory)", "status": "done"},
    {"title": "Phase 4 — Planning entities + essential UI", "status": "done"},
    {"title": "Phase 4b — Finish the MVP data model", "status": "done"},
    {"title": "Phase 5 — Rich documents (Tiptap editor)", "status": "done"},
    {"title": "Phase 6A — AI Context Pack Builder", "status": "done"},
    {"title": "Phase 7A — Approval engine + local queue", "status": "done"},
    {"title": "Phase 7B — STDIO MCP (read + propose)", "status": "done"},
    {"title": "Phase 7C0 — Framework-neutral exception boundary", "status": "done"},
    {"title": "Phase 7C1 — External HTTP API (disabled by default)", "status": "done"},
    {"title": "Phase 7C2a — Static GPT Actions OpenAPI contract", "status": "done"},
    {"title": "Phase 7C2b — User-authorized private GPT go-live", "status": "planned"},
    {"title": "Phase 8 — Read-only Git context + MVP release gate", "status": "done"},
    {"title": "Phase 9 — V1 interface expansion + notifications", "status": "done"},
    {"title": "Phase 10 — Discovery: local AI control plane (specs only, ≠ shipped hosted P10.x)", "status": "done"},
    {"title": "Phase 11 — LAN team mode (local server, one canonical DB)", "status": "done"},
    {"title": "Phase 12 — Repo cockpit: live local Git + GitHub visuals (show, don't do)", "status": "done"},
    {"title": "Phase 13 — Local canvas (Miro/Canva-like, fully offline)", "status": "done"},
    {"title": "Phase 14 — Hosted/SaaS mode (deferred; gated architecture review)", "status": "planned"},
    {"title": "Phase 15 — Boards, roadmap, timeline & calendar (15.0-15.12)", "status": "done"},
    {"title": "Phase 16 — Team administration & attribution (D29-D35)", "status": "done"},
    {"title": "Phase 17 — Integration hub (D36-D40)", "status": "done"},
    {"title": "Phase 18 — Notifications & backup (D41-D44)", "status": "done"},
]

# Project-level milestones.
MILESTONES: list[dict] = [
    {"title": "MVP + V1 feature-complete", "status": "achieved"},
    {"title": "OSS public launch", "status": "planned"},
    {"title": "Hosted SaaS beta", "status": "planned"},
]


def _seed(session: Session) -> Project:
    ws = session.exec(
        select(Workspace).where(
            Workspace.slug.in_((WORKSPACE_SLUG, *LEGACY_SLUGS))
        )
    ).first()
    if ws is None:
        ws = workspace_service.create_workspace(
            session,
            WorkspaceCreate(
                name="Planarus",
                slug=WORKSPACE_SLUG,
                description="Planarus dogfoods itself — this is the live project.",
            ),
        )

    project = project_service.create_project(
        session,
        ProjectCreate(
            workspace_id=ws.id,
            title="Planarus",
            slug=PROJECT_SLUG,
            summary="AI agents propose. You approve. — local-first AI project cockpit.",
            status="active",
        ),
    )

    for p in PHASES:
        phase_service.create_phase(
            session, project.id, PhaseCreate(title=p["title"], status=p["status"])
        )

    for m in MILESTONES:
        milestone_service.create_milestone(
            session,
            project.id,
            MilestoneCreate(title=m["title"], status=m["status"]),
        )
    return project


def main() -> int:
    with Session(engine) as session:
        existing = session.exec(
            select(Project).where(
                Project.slug.in_((PROJECT_SLUG, *LEGACY_SLUGS))
            )
        ).first()
        if existing is not None:
            print(
                f"Planarus project already seeded (id={existing.id}); nothing to do."
            )
            return 0
        project = _seed(session)
        project_id = project.id  # read before the session closes (avoids detach)

    print(
        f"Seeded Planarus project (id={project_id}): "
        f"{len(PHASES)} phases, {len(MILESTONES)} milestones. "
        f"Open the app to follow along."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
