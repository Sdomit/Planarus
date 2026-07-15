"""Seed a running Approvo database with the Approvo project itself (dogfooding).

Approvo manages Approvo: this loads the real roadmap — phases, the Phase 10
slices as stages, follow-up tasks, and launch milestones — into a running DB so
you can follow progress in the app's Roadmap / Task Board instead of only the
Markdown context pack. Kept in sync with context/NEXT_STEP.md each slice.

Idempotent at the project level: if the ``approvo`` project already exists it
does nothing (re-running is safe). Run against a **migrated** DB — the app applies
migrations on startup, or run ``alembic upgrade head`` first. Honors
``AGENTBOARD_DATABASE_URL`` / ``DATABASE_URL`` like the rest of the app.

    cd apps/api && python scripts/seed_approvo_project.py
"""
import sys

from sqlmodel import Session, select

from app.db.session import engine
from app.models.project import Project
from app.models.workspace import Workspace
from app.schemas.milestone import MilestoneCreate
from app.schemas.phase import PhaseCreate
from app.schemas.project import ProjectCreate
from app.schemas.stage import StageCreate
from app.schemas.task import TaskCreate
from app.schemas.workspace import WorkspaceCreate
from app.services import (
    milestone_service,
    phase_service,
    project_service,
    stage_service,
    task_service,
    workspace_service,
)

WORKSPACE_SLUG = "approvo"
PROJECT_SLUG = "approvo"

# (title, status). Phases 1–9 + 4b are done; Phase 10 (hosted/SaaS) is active.
PHASES: list[dict] = [
    {"title": "Phase 1 — Foundation", "status": "done"},
    {"title": "Phase 2 — Project CRUD", "status": "done"},
    {"title": "Phase 3 — Filesystem memory + context generation", "status": "done"},
    {"title": "Phase 4 — Planning entities", "status": "done"},
    {"title": "Phase 4b — MVP data model (milestone/checklist/comment/link)", "status": "done"},
    {"title": "Phase 5 — Rich docs (Tiptap)", "status": "done"},
    {"title": "Phase 6A — AI context pack builder", "status": "done"},
    {"title": "Phase 7 — Approvals + MCP + external API", "status": "done"},
    {"title": "Phase 8 — Read-only Git context", "status": "done"},
    {"title": "Phase 9 — V1 interface + notifications", "status": "done"},
    {
        "title": "Phase 10 — Hosted / SaaS",
        "status": "active",
        # slices modeled as stages; blocked = gated on local product validation
        "stages": [
            {"title": "P10.0 — Postgres-portability harness", "status": "done"},
            {
                "title": "P10.1 — Identity + workspace membership",
                "status": "done",
                "tasks": [
                    {"title": "Identity models + migration 0010", "status": "done"},
                    {"title": "Auth core + endpoints + membership RBAC", "status": "done"},
                    {"title": "Tests + Postgres verify + docs", "status": "done"},
                ],
            },
            {
                "title": "P10.2 — Tenant enforcement (workspace/project + D22)",
                "status": "done",
                "tasks": [
                    {"title": "Request-scoped tenant context from session", "status": "done"},
                    {"title": "Workspace/project access filtering + role gating", "status": "done"},
                    {"title": "Approver-role gating on approve/apply (D22)", "status": "done"},
                ],
            },
            {
                "title": "P10.2b — Per-child-route tenant guards (full isolation)",
                "status": "active",
                "tasks": [
                    {"title": "Guard nested collection routes (/projects/{id}/…)", "status": "backlog"},
                    {"title": "Resolve-via-parent on flat item routes (/tasks/{id}…)", "status": "backlog"},
                    {"title": "Cross-tenant denial sweep test over every domain route", "status": "backlog"},
                ],
            },
            {"title": "P10.3 — Hosted object storage adapter", "status": "planned"},
            {"title": "P10.4 — Hosted deploy shape", "status": "planned"},
            {"title": "P10.5 — SQLite→Postgres ETL (gated on validation)", "status": "blocked"},
            {"title": "P10.6 — Sync (gated on validation)", "status": "blocked"},
        ],
    },
]

# Project-level milestones.
MILESTONES: list[dict] = [
    {"title": "MVP + V1 feature-complete", "status": "achieved"},
    {"title": "OSS public launch", "status": "planned"},
    {"title": "Hosted SaaS beta", "status": "planned"},
]


def _seed(session: Session) -> Project:
    ws = session.exec(
        select(Workspace).where(Workspace.slug == WORKSPACE_SLUG)
    ).first()
    if ws is None:
        ws = workspace_service.create_workspace(
            session,
            WorkspaceCreate(
                name="Approvo",
                slug=WORKSPACE_SLUG,
                description="Approvo dogfoods itself — this is the live project.",
            ),
        )

    project = project_service.create_project(
        session,
        ProjectCreate(
            workspace_id=ws.id,
            title="Approvo",
            slug=PROJECT_SLUG,
            summary="AI agents propose. You approve. — local-first AI project cockpit.",
            status="active",
        ),
    )

    for p in PHASES:
        phase = phase_service.create_phase(
            session, project.id, PhaseCreate(title=p["title"], status=p["status"])
        )
        for s in p.get("stages", []):
            stage = stage_service.create_stage(
                session,
                project.id,
                StageCreate(phase_id=phase.id, title=s["title"], status=s["status"]),
            )
            for t in s.get("tasks", []):
                task_service.create_task(
                    session,
                    project.id,
                    TaskCreate(
                        title=t["title"],
                        status=t["status"],
                        phase_id=phase.id,
                        stage_id=stage.id,
                    ),
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
            select(Project).where(Project.slug == PROJECT_SLUG)
        ).first()
        if existing is not None:
            print(
                f"Approvo project already seeded (id={existing.id}); nothing to do."
            )
            return 0
        project = _seed(session)
        project_id = project.id  # read before the session closes (avoids detach)

    n_phases = len(PHASES)
    n_stages = sum(len(p.get("stages", [])) for p in PHASES)
    n_tasks = sum(
        len(s.get("tasks", [])) for p in PHASES for s in p.get("stages", [])
    )
    print(
        f"Seeded Approvo project (id={project_id}): "
        f"{n_phases} phases, {n_stages} stages, {n_tasks} tasks, "
        f"{len(MILESTONES)} milestones. Open the app to follow along."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
