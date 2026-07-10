from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.timeline import ProjectTimeline
from app.services import timeline_service

router = APIRouter()


@router.get("/projects/{project_id}/timeline", response_model=ProjectTimeline)
def get_timeline(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> ProjectTimeline:
    try:
        return timeline_service.build_timeline(session, project_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
