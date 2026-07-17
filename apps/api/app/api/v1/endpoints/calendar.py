from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.calendar_event import ProjectCalendar
from app.services import calendar_service

router = APIRouter()


@router.get("/projects/{project_id}/calendar", response_model=ProjectCalendar)
def get_calendar(
    project_id: str,
    date_from: Optional[str] = Query(default=None, alias="from"),
    date_to: Optional[str] = Query(default=None, alias="to"),
    session: Session = Depends(get_session),
) -> ProjectCalendar:
    """Aggregated calendar feed: events + dated milestones + due tasks in range."""
    try:
        return calendar_service.build_calendar(
            session, project_id, date_from=date_from, date_to=date_to
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )


@router.get("/projects/{project_id}/calendar.ics")
def get_calendar_ics(
    project_id: str,
    date_from: Optional[str] = Query(default=None, alias="from"),
    date_to: Optional[str] = Query(default=None, alias="to"),
    session: Session = Depends(get_session),
) -> Response:
    """Same aggregated feed as an iCalendar (.ics) download for external apps."""
    try:
        ics = calendar_service.build_ics(
            session, project_id, date_from=date_from, date_to=date_to
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="calendar-{project_id}.ics"'
        },
    )
