from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.core.exceptions import NotFoundError
from app.core.utils import new_id, now_utc
from app.models.agent_run import AgentRun
from app.models.project import Project
from app.schemas.agent_run import AgentRunAnalytics, AgentRunCreate, AgentRunUpdate
from app.services.audit_service import create_audit_event

_TERMINAL = {"succeeded", "failed", "canceled"}


def list_agent_runs(
    session: Session, project_id: str, limit: int | None = None
) -> list[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())  # type: ignore[attr-defined]
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.exec(stmt).all())


def create_agent_run(session: Session, project_id: str, data: AgentRunCreate) -> AgentRun:
    if session.get(Project, project_id) is None:
        raise NotFoundError(f"project '{project_id}' not found")

    now = now_utc()
    ended_at = data.ended_at
    if data.status in _TERMINAL and ended_at is None:
        ended_at = now
    run = AgentRun(
        id=new_id("run"),
        project_id=project_id,
        agent_family=data.agent_family,
        agent_name=data.agent_name,
        mode=data.mode,
        status=data.status,
        summary=data.summary,
        started_at=data.started_at or now,
        ended_at=ended_at,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="agent_run",
        entity_id=run.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(run)
    return run


def update_agent_run(
    session: Session, run_id: str, data: AgentRunUpdate
) -> Optional[AgentRun]:
    run = session.get(AgentRun, run_id)
    if run is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = now_utc()
    for key, value in update_data.items():
        setattr(run, key, value)
    if "ended_at" not in update_data:
        if run.status in _TERMINAL and run.ended_at is None:
            run.ended_at = now
        elif run.status == "started":
            run.ended_at = None  # reopened — a running run has no end time
    run.updated_at = now
    session.add(run)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="agent_run",
        entity_id=run_id,
        project_id=run.project_id,
    )
    session.commit()
    session.refresh(run)
    return run


def _duration_minutes(run: AgentRun) -> Optional[float]:
    if not run.ended_at:
        return None
    try:
        started = datetime.fromisoformat(run.started_at)
        ended = datetime.fromisoformat(run.ended_at)
        seconds = (ended - started).total_seconds()
    except (ValueError, TypeError):  # unparseable or naive/aware mix
        return None
    if seconds < 0:
        return None
    return seconds / 60.0


def build_analytics(session: Session, project_id: str) -> AgentRunAnalytics:
    if session.get(Project, project_id) is None:
        raise NotFoundError(f"project '{project_id}' not found")

    runs = list_agent_runs(session, project_id)
    by_family: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    durations: list[float] = []
    for run in runs:
        by_family[run.agent_family] = by_family.get(run.agent_family, 0) + 1
        by_status[run.status] = by_status.get(run.status, 0) + 1
        if run.mode:
            by_mode[run.mode] = by_mode.get(run.mode, 0) + 1
        minutes = _duration_minutes(run)
        if minutes is not None:
            durations.append(minutes)

    succeeded = by_status.get("succeeded", 0)
    failed = by_status.get("failed", 0)
    decided = succeeded + failed
    return AgentRunAnalytics(
        project_id=project_id,
        generated_at=now_utc(),
        total=len(runs),
        by_family=by_family,
        by_status=by_status,
        by_mode=by_mode,
        success_rate=round(succeeded / decided, 3) if decided else None,
        avg_duration_minutes=(
            round(sum(durations) / len(durations), 1) if durations else None
        ),
        last_run_at=runs[0].started_at if runs else None,
    )
