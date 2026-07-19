"""Runtime settings (Phase 9B) — local UI only.

GET is an unauthenticated local read that never discloses a secret or raw host.
PUT is local-control-gated (like api-clients / notification-rules) because a
switch changes a connection's effective state. Only switch-tier keys are writable;
the env ceiling always wins and is never editable here.

P16.1 (D35): with auth on, PUT additionally requires a **server admin** — the
control token is a CSRF guard the served web app hands to every browser, so on
a LAN it alone would let any signed-in teammate flip server switches. Local
mode (auth off) is unchanged.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.config import settings as env
from app.core.security import require_local_control
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
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
    user: Optional[User] = Depends(tenant_user),
) -> SettingsRead:
    if env.auth_enabled and (user is None or not user.is_admin):
        raise HTTPException(status_code=403, detail="server admin required")
    return settings_service.write_settings(session, data)
