from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.stage import StageCreate, StageRead, StageUpdate
from app.services import stage_service

router = APIRouter()


@router.get("/projects/{project_id}/stages", response_model=list[StageRead])
def list_stages(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[StageRead]:
    return stage_service.list_stages(session, project_id)


@router.post(
    "/projects/{project_id}/stages",
    response_model=StageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_stage(
    project_id: str,
    data: StageCreate,
    session: Session = Depends(get_session),
) -> StageRead:
    try:
        return stage_service.create_stage(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/stages/{stage_id}", response_model=StageRead)
def update_stage(
    stage_id: str,
    data: StageUpdate,
    session: Session = Depends(get_session),
) -> StageRead:
    stage = stage_service.update_stage(session, stage_id, data)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    return stage
