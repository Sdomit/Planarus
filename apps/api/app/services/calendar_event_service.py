from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.calendar_event import CalendarEvent
from app.models.phase import Phase
from app.models.project import Project
from app.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate
from app.services.audit_service import create_audit_event


def list_calendar_events(session: Session, project_id: str) -> list[CalendarEvent]:
    stmt = (
        select(CalendarEvent)
        .where(CalendarEvent.project_id == project_id)
        .order_by(CalendarEvent.start_at, CalendarEvent.id)
    )
    return list(session.exec(stmt).all())


def _validate_phase(session: Session, project_id: str, phase_id: Optional[str]) -> None:
    if phase_id is None:
        return
    phase = session.get(Phase, phase_id)
    if phase is None or phase.project_id != project_id:
        raise LookupError(f"phase '{phase_id}' not found in project '{project_id}'")


def create_calendar_event(
    session: Session, project_id: str, data: CalendarEventCreate
) -> CalendarEvent:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    _validate_phase(session, project_id, data.phase_id)

    now = now_utc()
    event = CalendarEvent(
        id=new_id("cal"),
        project_id=project_id,
        phase_id=data.phase_id,
        title=data.title,
        description=data.description,
        location=data.location,
        status=data.status,
        start_at=data.start_at,
        end_at=data.end_at,
        all_day=data.all_day,
        recurrence=data.recurrence,
        recurrence_until=data.recurrence_until,
        created_at=now,
        updated_at=now,
    )
    session.add(event)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="calendar_event",
        entity_id=event.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(event)
    return event


def update_calendar_event(
    session: Session, event_id: str, data: CalendarEventUpdate
) -> Optional[CalendarEvent]:
    event = session.get(CalendarEvent, event_id)
    if event is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "phase_id" in update_data:
        _validate_phase(session, event.project_id, update_data["phase_id"])

    for key, value in update_data.items():
        setattr(event, key, value)
    event.updated_at = now_utc()
    session.add(event)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="calendar_event",
        entity_id=event_id,
        project_id=event.project_id,
    )
    session.commit()
    session.refresh(event)
    return event


def delete_calendar_event(session: Session, event_id: str) -> bool:
    event = session.get(CalendarEvent, event_id)
    if event is None:
        return False
    project_id = event.project_id
    session.delete(event)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="calendar_event",
        entity_id=event_id,
        project_id=project_id,
    )
    session.commit()
    return True
