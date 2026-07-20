"""Verified local database backups (Phase 18.0) — local UI only.

Never mounted on the external API or MCP: a backup is a server-management
operation, like Settings. Both routes are local-control-gated, and with auth on
they additionally require a **server admin** — the same D35 reasoning the
Settings PUT uses: the control token is a CSRF guard the served web app hands to
every browser, so on a LAN it alone would let any signed-in teammate trigger
backups or enumerate them. Local single-user mode (auth off) is unchanged.

Responses carry file names only; the backup directory is server config.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.config import settings as env
from app.core.security import require_local_control
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.backups import BackupFile, BackupResult
from app.services import backup_service

router = APIRouter()


def _require_server_admin(user: Optional[User]) -> None:
    if env.auth_enabled and (user is None or not user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="server admin required")


@router.get(
    "/backups",
    response_model=list[BackupFile],
    dependencies=[Depends(require_local_control)],
)
def list_backups(user: Optional[User] = Depends(tenant_user)) -> list[BackupFile]:
    _require_server_admin(user)
    return backup_service.list_backups()


@router.post(
    "/backups",
    response_model=BackupResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_local_control)],
)
def create_backup(
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> BackupResult:
    _require_server_admin(user)
    return backup_service.create_backup(session)
