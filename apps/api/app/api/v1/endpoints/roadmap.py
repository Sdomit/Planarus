from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.roadmap import ProjectRoadmap
from app.services import roadmap_service

router = APIRouter()


@router.get("/projects/{project_id}/roadmap", response_model=ProjectRoadmap)
def get_roadmap(
    project_id: str,
    session: Session = Depends(get_session),
) -> ProjectRoadmap:
    try:
        return roadmap_service.build_roadmap(session, project_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
