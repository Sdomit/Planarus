"""Project-scoped, opt-in automatic approval of proposals.

Only the local-control approval endpoint can enable the switch. The API process
sweeps pending proposals even when no browser is open, and resumes after restart.
Every proposal still passes the ordinary approve and apply policy/staleness checks.
"""
from __future__ import annotations

import logging

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlmodel import Session, select

from app.db.session import engine
from app.models.approval_request import ApprovalRequest
from app.models.project import Project
from app.models.setting import Setting
from app.services import approval_service, settings_service
from app.services.audit_service import create_audit_event

logger = logging.getLogger("planarus.approval_auto_accept")
_PREFIX = "approval_auto_accept:"
_BATCH_SIZE = 100


def _key(project_id: str) -> str:
    return f"{_PREFIX}{project_id}"


def enabled(session: Session, project_id: str) -> bool:
    return settings_service.get_setting(session, _key(project_id), False) is True


def set_enabled(session: Session, project: Project, value: bool) -> None:
    settings_service.set_setting(session, _key(project.id), value)
    create_audit_event(
        session,
        event_type="approval_auto_accept_enabled" if value else "approval_auto_accept_disabled",
        actor_type="human",
        entity_type="project",
        entity_id=project.id,
        workspace_id=project.workspace_id,
        project_id=project.id,
    )
    session.commit()


def _process_one(project_id: str, approval_id: str) -> None:
    # A fresh session for each row sees a switch-off immediately and prevents a
    # stale identity-map value from keeping the sweep active.
    with Session(engine) as session:
        if not enabled(session, project_id):
            return
        ar = session.get(ApprovalRequest, approval_id)
        if ar is None or ar.project_id != project_id:
            return
        try:
            if ar.status == "pending":
                approval_service.approve(
                    session, ar.id, decided_by="auto", actor_type="system"
                )
            elif ar.status != "approved":
                return
            # Recheck before apply in case the owner switched the setting off
            # while approve was running. An already-started apply can finish.
            session.expire_all()
            if enabled(session, project_id):
                approval_service.apply(session, approval_id, actor_type="system")
        except Exception:  # noqa: BLE001 — per-row failure must not stop the queue
            logger.exception("auto accept failed for approval %s", approval_id)
            session.rollback()


def sweep() -> None:
    """Process up to one batch per enabled project; the next tick continues.

    Missing schema during first-run migration is harmless: the next tick will
    read it once the API has been migrated. No switch is enabled by default.
    """
    try:
        with Session(engine) as session:
            keys = session.exec(
                select(Setting.key).where(
                    Setting.key.like(f"{_PREFIX}%"), Setting.value == "true"
                )
            ).all()
            project_ids = [key[len(_PREFIX):] for key in keys]
        for project_id in project_ids:
            with Session(engine) as session:
                project = session.get(Project, project_id)
                # A Normal-mode project does not accept agent proposals.
                if project is None or project.mode == "normal":
                    continue
                approval_ids = session.exec(
                    select(ApprovalRequest.id)
                    .where(
                        ApprovalRequest.project_id == project_id,
                        ApprovalRequest.status.in_(("pending", "approved")),
                    )
                    .order_by(ApprovalRequest.created_at, ApprovalRequest.id)
                    .limit(_BATCH_SIZE)
                ).all()
            for approval_id in approval_ids:
                _process_one(project_id, approval_id)
    except (OperationalError, ProgrammingError):
        logger.debug("auto accept sweep waiting for database schema")
