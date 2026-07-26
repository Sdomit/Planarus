from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.schemas.risk import RiskCreate, RiskUpdate
from app.services import entity_connection_service, status_option_service
from app.services.audit_service import create_audit_event
from app.services.planning_reorder import apply_reorder

_CLOSED_STATUSES = frozenset({"mitigated", "accepted", "closed"})
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _validate_status(session: Session, project_id: str, status: str) -> None:
    if status not in status_option_service.allowed_status_keys(session, project_id, "risk"):
        raise ValueError(f"status '{status}' is not defined for this project")


def list_risks(session: Session, project_id: str) -> list[Risk]:
    # Manual order (sort_order) is primary; severity is the tiebreak so
    # un-reordered projects keep today's severity-first behavior.
    risks = list(
        session.exec(select(Risk).where(Risk.project_id == project_id)).all()
    )
    risks.sort(key=lambda r: (r.sort_order, _SEVERITY_ORDER.get(r.severity, 99), r.id))
    return risks


def get_risk(session: Session, risk_id: str) -> Optional[Risk]:
    return session.get(Risk, risk_id)


def _validate_phase(session: Session, project_id: str, phase_id: Optional[str]) -> None:
    if phase_id is None:
        return
    phase = session.get(Phase, phase_id)
    if phase is None or phase.project_id != project_id:
        raise LookupError(f"phase '{phase_id}' not found in project '{project_id}'")


def create_risk(session: Session, project_id: str, data: RiskCreate) -> Risk:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    _validate_status(session, project_id, data.status)
    _validate_phase(session, project_id, data.phase_id)

    now = now_utc()
    risk = Risk(
        id=new_id("rsk"),
        project_id=project_id,
        phase_id=data.phase_id,
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
    if update_data.get("status") is not None:
        _validate_status(session, risk.project_id, update_data["status"])
    if "phase_id" in update_data:
        _validate_phase(session, risk.project_id, update_data["phase_id"])
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
    entity_connection_service.delete_for_entity(session, project_id, "risk", risk_id)
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


def reorder_risks(session: Session, project_id: str, ids: list[str]) -> list[Risk]:
    if session.get(Project, project_id) is None:
        raise LookupError(f"project '{project_id}' not found")
    rows = {r.id: r for r in list_risks(session, project_id)}
    return apply_reorder(
        session, project_id=project_id, entity_type="risk", rows=rows, ids=ids
    )
