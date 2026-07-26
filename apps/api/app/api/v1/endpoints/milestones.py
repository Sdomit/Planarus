from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.milestone import MilestoneCreate, MilestoneRead, MilestoneUpdate
from app.schemas.reorder import ReorderRequest
from app.services import milestone_service

router = APIRouter()


@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneRead])
def list_milestones(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[MilestoneRead]:
    return milestone_service.list_milestones(session, project_id)


@router.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone(
    project_id: str,
    data: MilestoneCreate,
    session: Session = Depends(get_session),
) -> MilestoneRead:
    return milestone_service.create_milestone(session, project_id, data)


@router.patch("/milestones/{milestone_id}", response_model=MilestoneRead)
def update_milestone(
    milestone_id: str,
    data: MilestoneUpdate,
    session: Session = Depends(get_session),
) -> MilestoneRead:
    milestone = milestone_service.update_milestone(session, milestone_id, data)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found"
        )
    return milestone


@router.post(
    "/projects/{project_id}/milestones/reorder", response_model=list[MilestoneRead]
)
def reorder_milestones(
    project_id: str,
    data: ReorderRequest,
    session: Session = Depends(get_session),
) -> list[MilestoneRead]:
    return milestone_service.reorder_milestones(session, project_id, data.ids)


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(
    milestone_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not milestone_service.delete_milestone(session, milestone_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found"
        )
