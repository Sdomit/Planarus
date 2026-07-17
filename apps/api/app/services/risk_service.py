from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.project import Project
from app.models.risk import Risk
from app.schemas.risk import RiskCreate, RiskUpdate
from app.services.audit_service import create_audit_event

_CLOSED_STATUSES = frozenset({"mitigated", "accepted", "closed"})
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def list_risks(session: Session, project_id: str) -> list[Risk]:
    risks = list(
        session.exec(select(Risk).where(Risk.project_id == project_id)).all()
    )
    risks.sort(key=lambda r: (_SEVERITY_ORDER.get(r.severity, 99), r.id))
    return risks


def get_risk(session: Session, risk_id: str) -> Optional[Risk]:
    return session.get(Risk, risk_id)


def create_risk(session: Session, project_id: str, data: RiskCreate) -> Risk:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    now = now_utc()
    risk = Risk(
        id=new_id("rsk"),
        project_id=project_id,
        title=data.title,
        description=data.description,
        severity=data.severity,
        status=data.status,
        mitigation=data.mitigation,
        created_at=now,
        updated_at=now,
    )
    session.add(risk)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="risk",
        entity_id=risk.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(risk)
    return risk


def update_risk(session: Session, risk_id: str, data: RiskUpdate) -> Optional[Risk]:
    risk = session.get(Risk, risk_id)
    if risk is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = now_utc()
    for key, value in update_data.items():
        setattr(risk, key, value)
    risk.updated_at = now
    session.add(risk)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="risk",
        entity_id=risk_id,
        project_id=risk.project_id,
    )
    session.commit()
    session.refresh(risk)
    return risk


def delete_risk(session: Session, risk_id: str) -> bool:
    risk = session.get(Risk, risk_id)
    if risk is None:
        return False
    project_id = risk.project_id
    session.delete(risk)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="risk",
        entity_id=risk_id,
        project_id=project_id,
    )
    session.commit()
    return True
