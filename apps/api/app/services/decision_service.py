from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.decision import Decision
from app.models.phase import Phase
from app.models.project import Project
from app.schemas.decision import DecisionCreate, DecisionUpdate
from app.services import status_option_service
from app.services.audit_service import create_audit_event
from app.services.planning_reorder import apply_reorder


def _validate_status(session: Session, project_id: str, status: str) -> None:
    if status not in status_option_service.allowed_status_keys(session, project_id, "decision"):
        raise ValueError(f"status '{status}' is not defined for this project")


def list_decisions(session: Session, project_id: str) -> list[Decision]:
    # Manual order (sort_order) is primary; newest-first is the tiebreak so
    # un-reordered projects keep today's behavior.
    stmt = (
        select(Decision)
        .where(Decision.project_id == project_id)
        .order_by(Decision.sort_order, Decision.created_at.desc(), Decision.id)
    )
    return list(session.exec(stmt).all())


def get_decision(session: Session, decision_id: str) -> Optional[Decision]:
    return session.get(Decision, decision_id)


def _validate_phase(session: Session, project_id: str, phase_id: Optional[str]) -> None:
    if phase_id is None:
        return
    phase = session.get(Phase, phase_id)
    if phase is None or phase.project_id != project_id:
        raise LookupError(f"phase '{phase_id}' not found in project '{project_id}'")


def create_decision(
    session: Session, project_id: str, data: DecisionCreate
) -> Decision:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    _validate_status(session, project_id, data.status)
    _validate_phase(session, project_id, data.phase_id)

    now = now_utc()
    decision = Decision(
        id=new_id("dec"),
        project_id=project_id,
        phase_id=data.phase_id,
        title=data.title,
        context=data.context,
        decision=data.decision,
        status=data.status,
        created_at=now,
        updated_at=now,
    )
    session.add(decision)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="decision",
        entity_id=decision.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(decision)
    return decision


def update_decision(
    session: Session, decision_id: str, data: DecisionUpdate
) -> Optional[Decision]:
    decision = session.get(Decision, decision_id)
    if decision is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("status") is not None:
        _validate_status(session, decision.project_id, update_data["status"])
    if "phase_id" in update_data:
        _validate_phase(session, decision.project_id, update_data["phase_id"])
    now = now_utc()
    for key, value in update_data.items():
        setattr(decision, key, value)
    decision.updated_at = now
    session.add(decision)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="decision",
        entity_id=decision_id,
        project_id=decision.project_id,
    )
    session.commit()
    session.refresh(decision)
    return decision


def delete_decision(session: Session, decision_id: str) -> bool:
    decision = session.get(Decision, decision_id)
    if decision is None:
        return False
    project_id = decision.project_id
    session.delete(decision)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="decision",
        entity_id=decision_id,
        project_id=project_id,
    )
    session.commit()
    return True


def reorder_decisions(
    session: Session, project_id: str, ids: list[str]
) -> list[Decision]:
    if session.get(Project, project_id) is None:
        raise LookupError(f"project '{project_id}' not found")
    rows = {d.id: d for d in list_decisions(session, project_id)}
    apply_reorder(
        session, project_id=project_id, entity_type="decision", rows=rows, ids=ids
    )
    return list_decisions(session, project_id)
