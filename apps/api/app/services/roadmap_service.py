from sqlmodel import Session, select

from app.core.exceptions import NotFoundError
from app.core.utils import now_utc
from app.models.phase import Phase
from app.models.project import Project
from app.models.stage import Stage
from app.models.task import Task
from app.schemas.roadmap import (
    ProjectRoadmap,
    RoadmapPhase,
    RoadmapStage,
    RoadmapTaskRollup,
)
from app.services import status_option_service


def _rollup(tasks: list[Task], categories: dict[str, str]) -> RoadmapTaskRollup:
    """Progress counts for one bucket of tasks.

    #88: `done` and `canceled` are resolved through the project's status
    categories, not by comparing the status string — a custom column marked as
    the done category counts as finished, which is the whole point of letting
    people rename their board. `in_progress`/`blocked` stay keyed to the
    built-ins: they name specific states, not a category, and no custom status
    can claim them.
    """
    active = [t for t in tasks if categories.get(t.status) != "canceled"]
    return RoadmapTaskRollup(
        total=len(active),
        done=sum(1 for t in active if categories.get(t.status) == "done"),
        in_progress=sum(1 for t in active if t.status == "in_progress"),
        blocked=sum(1 for t in active if t.status == "blocked"),
    )


def _pct(rollup: RoadmapTaskRollup) -> int:
    return round(100 * rollup.done / rollup.total) if rollup.total else 0


def build_roadmap(session: Session, project_id: str) -> ProjectRoadmap:
    if session.get(Project, project_id) is None:
        raise NotFoundError(f"project '{project_id}' not found")

    phases = list(
        session.exec(
            select(Phase)
            .where(Phase.project_id == project_id)
            .order_by(Phase.sort_order, Phase.id)
        ).all()
    )
    stages = list(
        session.exec(
            select(Stage)
            .where(Stage.project_id == project_id)
            .order_by(Stage.sort_order, Stage.id)
        ).all()
    )
    tasks = list(
        session.exec(select(Task).where(Task.project_id == project_id)).all()
    )

    # One category lookup for the whole roadmap (#88): every rollup below asks
    # the same project the same question.
    categories = status_option_service.status_categories(session, project_id, "task")

    stage_phase = {s.id: s.phase_id for s in stages}

    def phase_of(task: Task) -> str | None:
        if task.phase_id:
            return task.phase_id
        if task.stage_id:
            return stage_phase.get(task.stage_id)
        return None

    by_phase: dict[str | None, list[Task]] = {}
    by_stage: dict[str, list[Task]] = {}
    for t in tasks:
        by_phase.setdefault(phase_of(t), []).append(t)
        if t.stage_id:
            by_stage.setdefault(t.stage_id, []).append(t)

    roadmap_phases: list[RoadmapPhase] = []
    for phase in phases:
        stage_items: list[RoadmapStage] = []
        for stage in stages:
            if stage.phase_id != phase.id:
                continue
            srollup = _rollup(by_stage.get(stage.id, []), categories)
            stage_items.append(
                RoadmapStage(
                    id=stage.id,
                    title=stage.title,
                    status=stage.status,
                    sort_order=stage.sort_order,
                    tasks=srollup,
                    pct_done=_pct(srollup),
                )
            )
        prollup = _rollup(by_phase.get(phase.id, []), categories)
        roadmap_phases.append(
            RoadmapPhase(
                id=phase.id,
                title=phase.title,
                status=phase.status,
                sort_order=phase.sort_order,
                stages=stage_items,
                tasks=prollup,
                pct_done=_pct(prollup),
            )
        )

    unphased = _rollup(by_phase.get(None, []), categories)
    totals = _rollup(tasks, categories)
    return ProjectRoadmap(
        project_id=project_id,
        generated_at=now_utc(),
        phases=roadmap_phases,
        unphased=unphased,
        totals=totals,
        pct_done=_pct(totals),
    )
