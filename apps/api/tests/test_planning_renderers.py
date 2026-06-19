"""Tests for the Phase 4 data-driven renderers (ROADMAP, TASKS, DECISIONS, RISKS).

These tests construct a RenderContext with seeded planning entity objects and
verify that the rendered output contains the expected content — without relying
on golden files (that job belongs to test_golden_files.py).
"""
from __future__ import annotations

from app.fsmemory.renderers import RenderContext, render
from app.fsmemory.spec import CONTEXT_FILES
from app.models.blocker import Blocker
from app.models.decision import Decision
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.task import Task
from app.models.workspace import Workspace

FIXED_TS = "2026-06-19T00:00:00+00:00"
FIXED_TS2 = "2026-06-20T00:00:00+00:00"


def _spec(filename: str):
    return next(s for s in CONTEXT_FILES if s.filename == filename)


def _ws() -> Workspace:
    return Workspace(
        id="ws_t",
        name="Test WS",
        slug="test-ws",
        created_at=FIXED_TS,
        updated_at=FIXED_TS,
    )


def _proj() -> Project:
    return Project(
        id="proj_t",
        workspace_id="ws_t",
        title="Test Project",
        slug="test-project",
        status="active",
        created_at=FIXED_TS,
        updated_at=FIXED_TS,
    )


def _ctx(**kwargs) -> RenderContext:
    return RenderContext(project=_proj(), workspace=_ws(), updated_at=FIXED_TS, **kwargs)


# ── ROADMAP.md ──────────────────────────────────────────────────────────────


def test_roadmap_empty() -> None:
    rendered = render(_spec("ROADMAP.md"), _ctx())
    assert "# Roadmap" in rendered
    assert "## Phases" in rendered
    assert "_No phases yet._" in rendered
    assert "## Stages" in rendered
    assert "_No stages yet._" in rendered
    assert "## Milestones" in rendered


def test_roadmap_with_phases() -> None:
    phases = (
        Phase(
            id="ph_1",
            project_id="proj_t",
            title="Foundation",
            status="done",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
        Phase(
            id="ph_2",
            project_id="proj_t",
            title="Core Features",
            status="active",
            sort_order=2,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("ROADMAP.md"), _ctx(phases=phases))
    assert "Foundation" in rendered
    assert "Core Features" in rendered
    assert "done" in rendered
    assert "active" in rendered


def test_roadmap_with_stages() -> None:
    phases = (
        Phase(
            id="ph_1",
            project_id="proj_t",
            title="Ph1",
            status="active",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    stages = (
        Stage(
            id="stg_1",
            phase_id="ph_1",
            project_id="proj_t",
            title="Stage Alpha",
            status="planned",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("ROADMAP.md"), _ctx(phases=phases, stages=stages))
    assert "Stage Alpha" in rendered
    assert "Ph1" in rendered


def test_roadmap_sort_order() -> None:
    phases = (
        Phase(
            id="ph_z",
            project_id="proj_t",
            title="ZZZ",
            status="planned",
            sort_order=99,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
        Phase(
            id="ph_a",
            project_id="proj_t",
            title="AAA",
            status="planned",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("ROADMAP.md"), _ctx(phases=phases))
    aaa_pos = rendered.index("AAA")
    zzz_pos = rendered.index("ZZZ")
    assert aaa_pos < zzz_pos


# ── TASKS.md ──────────────────────────────────────────────────────────────


def test_tasks_empty() -> None:
    rendered = render(_spec("TASKS.md"), _ctx())
    assert "# Tasks" in rendered
    assert "Active (0)" in rendered
    assert "0 completed." in rendered
    assert "_No active tasks._" in rendered
    assert "_No open blockers._" in rendered


def test_tasks_with_active_and_done() -> None:
    tasks = (
        Task(
            id="tsk_1",
            project_id="proj_t",
            title="Active task",
            status="in_progress",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
        Task(
            id="tsk_2",
            project_id="proj_t",
            title="Done task",
            status="done",
            sort_order=2,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("TASKS.md"), _ctx(tasks=tasks))
    assert "Active (1)" in rendered
    assert "Active task" in rendered
    assert "1 completed." in rendered
    assert "Done task" not in rendered


def test_tasks_with_blockers() -> None:
    blockers = (
        Blocker(
            id="blk_1",
            project_id="proj_t",
            title="DB migration blocked",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("TASKS.md"), _ctx(blockers=blockers))
    assert "DB migration blocked" in rendered
    assert "open" in rendered


def test_tasks_resolved_blocker_not_shown() -> None:
    blockers = (
        Blocker(
            id="blk_1",
            project_id="proj_t",
            title="Old blocker",
            status="resolved",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("TASKS.md"), _ctx(blockers=blockers))
    assert "_No open blockers._" in rendered


# ── DECISIONS.md ──────────────────────────────────────────────────────────


def test_decisions_empty() -> None:
    rendered = render(_spec("DECISIONS.md"), _ctx())
    assert "# Decisions" in rendered
    assert "_No decisions recorded yet._" in rendered


def test_decisions_renders_entries() -> None:
    decisions = (
        Decision(
            id="dec_1",
            project_id="proj_t",
            title="Use SQLite",
            decision="SQLite for local-first MVP",
            status="accepted",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("DECISIONS.md"), _ctx(decisions=decisions))
    assert "Use SQLite" in rendered
    assert "SQLite for local-first MVP" in rendered
    assert "accepted" in rendered


def test_decisions_sorted_newest_first() -> None:
    decisions = (
        Decision(
            id="dec_1",
            project_id="proj_t",
            title="Older decision",
            decision="D1",
            status="accepted",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
        Decision(
            id="dec_2",
            project_id="proj_t",
            title="Newer decision",
            decision="D2",
            status="proposed",
            created_at=FIXED_TS2,
            updated_at=FIXED_TS2,
        ),
    )
    rendered = render(_spec("DECISIONS.md"), _ctx(decisions=decisions))
    newer_pos = rendered.index("Newer decision")
    older_pos = rendered.index("Older decision")
    assert newer_pos < older_pos


# ── RISKS.md ──────────────────────────────────────────────────────────────


def test_risks_empty() -> None:
    rendered = render(_spec("RISKS.md"), _ctx())
    assert "# Risks" in rendered
    assert "_None yet._" in rendered
    assert "0 closed." in rendered
    assert "_No open blockers._" in rendered


def test_risks_renders_open_risks() -> None:
    risks = (
        Risk(
            id="rsk_1",
            project_id="proj_t",
            title="Data loss",
            severity="high",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("RISKS.md"), _ctx(risks=risks))
    assert "Data loss" in rendered
    assert "high" in rendered
    assert "open" in rendered


def test_risks_sorted_by_severity() -> None:
    risks = (
        Risk(
            id="rsk_low",
            project_id="proj_t",
            title="Low risk",
            severity="low",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
        Risk(
            id="rsk_crit",
            project_id="proj_t",
            title="Critical risk",
            severity="critical",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
        Risk(
            id="rsk_high",
            project_id="proj_t",
            title="High risk",
            severity="high",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("RISKS.md"), _ctx(risks=risks))
    crit_pos = rendered.index("Critical risk")
    high_pos = rendered.index("High risk")
    low_pos = rendered.index("Low risk")
    assert crit_pos < high_pos < low_pos


def test_risks_closed_counted() -> None:
    risks = (
        Risk(
            id="rsk_1",
            project_id="proj_t",
            title="Old risk",
            severity="low",
            status="closed",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("RISKS.md"), _ctx(risks=risks))
    assert "1 closed." in rendered
    assert "Old risk" not in rendered  # closed risks not shown in open table


def test_risks_with_open_blockers() -> None:
    blockers = (
        Blocker(
            id="blk_1",
            project_id="proj_t",
            title="API blocked",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("RISKS.md"), _ctx(blockers=blockers))
    assert "API blocked" in rendered


# ── STATUS.md reflects planning data ──────────────────────────────────────


def test_status_shows_active_phase() -> None:
    phases = (
        Phase(
            id="ph_1",
            project_id="proj_t",
            title="Implementation Phase",
            status="active",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("STATUS.md"), _ctx(phases=phases))
    assert "Implementation Phase" in rendered


def test_status_no_active_phase() -> None:
    phases = (
        Phase(
            id="ph_1",
            project_id="proj_t",
            title="Done Phase",
            status="done",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    rendered = render(_spec("STATUS.md"), _ctx(phases=phases))
    assert "Active phase: none" in rendered


# ── Idempotency ────────────────────────────────────────────────────────────


def test_all_renderers_idempotent() -> None:
    phases = (
        Phase(
            id="ph_1",
            project_id="proj_t",
            title="P1",
            status="active",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    tasks = (
        Task(
            id="tsk_1",
            project_id="proj_t",
            title="T1",
            status="in_progress",
            sort_order=1,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    decisions = (
        Decision(
            id="dec_1",
            project_id="proj_t",
            title="D1",
            decision="Use X",
            status="accepted",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    risks = (
        Risk(
            id="rsk_1",
            project_id="proj_t",
            title="R1",
            severity="high",
            status="open",
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
        ),
    )
    ctx = _ctx(phases=phases, tasks=tasks, decisions=decisions, risks=risks)
    for spec in CONTEXT_FILES:
        first = render(spec, ctx)
        second = render(spec, ctx)
        assert first == second, f"idempotency failed for {spec.filename}"
