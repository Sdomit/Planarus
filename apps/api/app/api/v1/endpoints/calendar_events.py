from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.calendar_event import (
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
)
from app.services import calendar_event_service

router = APIRouter()


@router.get(
    "/projects/{project_id}/calendar-events",
    response_model=list[CalendarEventRead],
)
def list_calendar_events(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[CalendarEventRead]:
    return calendar_event_service.list_calendar_events(session, project_id)


@router.post(
    "/projects/{project_id}/calendar-events",
    response_model=CalendarEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_calendar_event(
    project_id: str,
    data: CalendarEventCreate,
    session: Session = Depends(get_session),
) -> CalendarEventRead:
    try:
        return calendar_event_service.create_calendar_event(session, project_id, data)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )


@router.patch("/calendar-events/{event_id}", response_model=CalendarEventRead)
def update_calendar_event(
    event_id: str,
    data: CalendarEventUpdate,
    session: Session = Depends(get_session),
) -> CalendarEventRead:
    event = calendar_event_service.update_calendar_event(session, event_id, data)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found"
        )
    return event


@router.delete(
    "/calendar-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_calendar_event(
    event_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not calendar_event_service.delete_calendar_event(session, event_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found"
        )
