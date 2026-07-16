"""Runtime settings (Phase 9B) — local UI only.

GET is an unauthenticated local read that never discloses a secret or raw host.
PUT is local-control-gated (like api-clients / notification-rules) because a
switch changes a connection's effective state. Only switch-tier keys are writable;
the env ceiling always wins and is never editable here.
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.security import require_local_control
from app.db.session import get_session
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.services import settings_service

router = APIRouter()


@router.get("/settings", response_model=SettingsRead)
def get_settings(session: Session = Depends(get_session)) -> SettingsRead:
    return settings_service.read_settings(session)


@router.put(
    "/settings",
    response_model=SettingsRead,
    dependencies=[Depends(require_local_control)],
)
def put_settings(
    data: SettingsUpdate,
    session: Session = Depends(get_session),
) -> SettingsRead:
    return settings_service.write_settings(session, data)
