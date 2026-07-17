from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.phase import PhaseCreate, PhaseRead, PhaseUpdate
from app.schemas.reorder import ReorderRequest
from app.services import phase_service

router = APIRouter()


@router.get("/projects/{project_id}/phases", response_model=list[PhaseRead])
def list_phases(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[PhaseRead]:
    return phase_service.list_phases(session, project_id)


@router.post(
    "/projects/{project_id}/phases",
    response_model=PhaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_phase(
    project_id: str,
    data: PhaseCreate,
    session: Session = Depends(get_session),
) -> PhaseRead:
    try:
        return phase_service.create_phase(session, project_id, data)
    except ValueError as exc:
        if "project" in str(exc) and "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.patch("/phases/{phase_id}", response_model=PhaseRead)
def update_phase(
    phase_id: str,
    data: PhaseUpdate,
    session: Session = Depends(get_session),
) -> PhaseRead:
    try:
        phase = phase_service.update_phase(session, phase_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if phase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phase not found")
    return phase


@router.post("/projects/{project_id}/phases/reorder", response_model=list[PhaseRead])
def reorder_phases(
    project_id: str,
    data: ReorderRequest,
    session: Session = Depends(get_session),
) -> list[PhaseRead]:
    try:
        return phase_service.reorder_phases(session, project_id, data.ids)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


@router.delete("/phases/{phase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_phase(
    phase_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not phase_service.delete_phase(session, phase_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phase not found")
