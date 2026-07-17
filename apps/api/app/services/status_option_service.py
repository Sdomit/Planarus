import re
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.constants import BUILTIN_STATUS_KEYS
from app.core.utils import new_id, now_utc
from app.models.decision import Decision
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.status_option import StatusOption
from app.models.task import Task
from app.schemas.status_option import (
    StatusOptionCreate,
    StatusOptionRead,
    StatusOptionUpdate,
)
from app.services.audit_service import create_audit_event

# entity_type → (model, status attribute) for "is this status in use?" checks.
_STATUS_MODELS = {
    "task": (Task, "status"),
    "phase": (Phase, "status"),
    "risk": (Risk, "status"),
    "milestone": (Milestone, "status"),
    "decision": (Decision, "status"),
}


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return s or "status"


def _builtin_reads(entity_type: str) -> list[StatusOptionRead]:
    keys = BUILTIN_STATUS_KEYS.get(entity_type, ())
    return [
        StatusOptionRead(
            id=None,
            key=k,
            label=k.replace("_", " ").capitalize(),
            color=None,
            sort_order=i,
            builtin=True,
        )
        for i, k in enumerate(keys)
    ]


def list_custom(session: Session, project_id: str, entity_type: str) -> list[StatusOption]:
    stmt = (
        select(StatusOption)
        .where(
            StatusOption.project_id == project_id,
            StatusOption.entity_type == entity_type,
        )
        .order_by(StatusOption.sort_order, StatusOption.id)
    )
    return list(session.exec(stmt).all())


def list_status_options(
    session: Session, project_id: str, entity_type: str
) -> list[StatusOptionRead]:
    """Built-in canonical statuses first, then this project's custom ones."""
    out = _builtin_reads(entity_type)
    base = len(out)
    for opt in list_custom(session, project_id, entity_type):
        out.append(
            StatusOptionRead(
                id=opt.id,
                key=opt.key,
                label=opt.label,
                color=opt.color,
                sort_order=base + opt.sort_order,
                builtin=False,
            )
        )
    return out


def allowed_status_keys(session: Session, project_id: str, entity_type: str) -> set[str]:
    """The set a `status` value may take: built-ins ∪ this project's custom keys."""
    keys = set(BUILTIN_STATUS_KEYS.get(entity_type, ()))
    keys.update(opt.key for opt in list_custom(session, project_id, entity_type))
    return keys


def create_status_option(
    session: Session, project_id: str, data: StatusOptionCreate
) -> StatusOption:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    key = _slug(data.label)
    taken = allowed_status_keys(session, project_id, data.entity_type)
    if key in taken:
        raise ValueError(f"a status '{key}' already exists")

    max_order = session.exec(
        select(func.max(StatusOption.sort_order)).where(
            StatusOption.project_id == project_id,
            StatusOption.entity_type == data.entity_type,
        )
    ).first()
    now = now_utc()
    opt = StatusOption(
        id=new_id("sto"),
        project_id=project_id,
        entity_type=data.entity_type,
        key=key,
        label=data.label,
        color=data.color,
        sort_order=(max_order or 0) + 1,
        created_at=now,
        updated_at=now,
    )
    session.add(opt)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="status_option",
        entity_id=opt.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(opt)
    return opt


def update_status_option(
    session: Session, option_id: str, data: StatusOptionUpdate
) -> Optional[StatusOption]:
    opt = session.get(StatusOption, option_id)
    if opt is None:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(opt, k, v)
    opt.updated_at = now_utc()
    session.add(opt)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="status_option",
        entity_id=option_id,
        project_id=opt.project_id,
    )
    session.commit()
    session.refresh(opt)
    return opt


def _usage_count(session: Session, opt: StatusOption) -> int:
    model, attr = _STATUS_MODELS[opt.entity_type]
    return len(
        session.exec(
            select(model).where(
                model.project_id == opt.project_id,
                getattr(model, attr) == opt.key,
            )
        ).all()
    )


def delete_status_option(session: Session, option_id: str) -> bool:
    opt = session.get(StatusOption, option_id)
    if opt is None:
        return False
    if _usage_count(session, opt) > 0:
        raise ValueError(
            "cannot delete a status that is still in use; move those cards first"
        )
    project_id = opt.project_id
    session.delete(opt)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="status_option",
        entity_id=option_id,
        project_id=project_id,
    )
    session.commit()
    return True
