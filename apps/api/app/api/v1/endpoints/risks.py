from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.risk import RiskCreate, RiskRead, RiskUpdate
from app.services import risk_service

router = APIRouter()


@router.get("/projects/{project_id}/risks", response_model=list[RiskRead])
def list_risks(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[RiskRead]:
    return risk_service.list_risks(session, project_id)


@router.post(
    "/projects/{project_id}/risks",
    response_model=RiskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_risk(
    project_id: str,
    data: RiskCreate,
    session: Session = Depends(get_session),
) -> RiskRead:
    try:
        return risk_service.create_risk(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/risks/{risk_id}", response_model=RiskRead)
def update_risk(
    risk_id: str,
    data: RiskUpdate,
    session: Session = Depends(get_session),
) -> RiskRead:
    risk = risk_service.update_risk(session, risk_id, data)
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    return risk
