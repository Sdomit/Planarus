from typing import Optional

from sqlmodel import Session, select

from app.core.utils import now_utc
from app.models.calendar_event import CalendarEvent
from app.models.milestone import Milestone
from app.models.project import Project
from app.models.task import Task
from app.schemas.calendar_event import CalendarItem, ProjectCalendar


def _in_range(start_at: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
    """Range filter on the date portion (YYYY-MM-DD) of an ISO start value.

    Comparing the 10-char date prefix keeps date-only and datetime values (and
    all-day vs timed items) on the same footing. `date_from`/`date_to` are
    inclusive YYYY-MM-DD bounds; either may be omitted.
    """
    day = start_at[:10]
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


def build_calendar(
    session: Session,
    project_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> ProjectCalendar:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    items: list[CalendarItem] = []

    for ev in session.exec(
        select(CalendarEvent).where(CalendarEvent.project_id == project_id)
    ).all():
        if not _in_range(ev.start_at, date_from, date_to):
            continue
        items.append(
            CalendarItem(
                id=f"event:{ev.id}",
                source="event",
                ref_id=ev.id,
                title=ev.title,
                start_at=ev.start_at,
                end_at=ev.end_at,
                all_day=ev.all_day,
                status=ev.status,
                phase_id=ev.phase_id,
            )
        )

    for ms in session.exec(
        select(Milestone).where(Milestone.project_id == project_id)
    ).all():
        if not ms.target_date or not _in_range(ms.target_date, date_from, date_to):
            continue
        items.append(
            CalendarItem(
                id=f"milestone:{ms.id}",
                source="milestone",
                ref_id=ms.id,
                title=ms.title,
                start_at=ms.target_date,
                end_at=None,
                all_day=True,
                status=ms.status,
                phase_id=ms.phase_id,
            )
        )

    for tk in session.exec(select(Task).where(Task.project_id == project_id)).all():
        if not tk.due_at or not _in_range(tk.due_at, date_from, date_to):
            continue
        items.append(
            CalendarItem(
                id=f"task:{tk.id}",
                source="task",
                ref_id=tk.id,
                title=tk.title,
                start_at=tk.due_at,
                end_at=None,
                all_day=True,
                status=tk.status,
                phase_id=tk.phase_id,
            )
        )

    items.sort(key=lambda it: (it.start_at, it.title))
    return ProjectCalendar(
        project_id=project_id, generated_at=now_utc(), items=items
    )
