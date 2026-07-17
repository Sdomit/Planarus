from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.decision import DecisionCreate, DecisionRead, DecisionUpdate
from app.schemas.reorder import ReorderRequest
from app.services import decision_service

router = APIRouter()


@router.get("/projects/{project_id}/decisions", response_model=list[DecisionRead])
def list_decisions(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    return decision_service.list_decisions(session, project_id)


@router.post(
    "/projects/{project_id}/decisions",
    response_model=DecisionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_decision(
    project_id: str,
    data: DecisionCreate,
    session: Session = Depends(get_session),
) -> DecisionRead:
    try:
        return decision_service.create_decision(session, project_id, data)
    except ValueError as exc:
        if "project" in str(exc) and "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.patch("/decisions/{decision_id}", response_model=DecisionRead)
def update_decision(
    decision_id: str,
    data: DecisionUpdate,
    session: Session = Depends(get_session),
) -> DecisionRead:
    try:
        decision = decision_service.update_decision(session, decision_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found"
        )
    return decision


@router.post(
    "/projects/{project_id}/decisions/reorder", response_model=list[DecisionRead]
)
def reorder_decisions(
    project_id: str,
    data: ReorderRequest,
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    try:
        return decision_service.reorder_decisions(session, project_id, data.ids)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


@router.delete("/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(
    decision_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not decision_service.delete_decision(session, decision_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found"
        )
