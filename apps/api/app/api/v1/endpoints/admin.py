"""Server-admin account management (Phase 16.1, D29/D31).

The admin plane: session cookie + server-admin flag on every route, plus the
local control token (CSRF guard) on every mutation — the same triple the other
management writes use. Mounted behind ``require_auth_enabled``, so in local
single-user mode the whole surface 404s and nothing changes.

Deliberately NOT under ``/api/external`` and never reachable with an ``agbk_``
key: external clients read and propose; they never administer (D31). Scripted
provisioning signs in as an admin service account and calls these routes with
its cookie — see docs/guide/team-administration.md.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth_deps import require_auth_enabled, require_server_admin
from app.core.exceptions import ConflictError
from app.core.security import require_local_control
from app.db.session import get_session
from app.models.user import User
from app.schemas.admin import (
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserCreated,
    AdminUserPatch,
    AdminUserRead,
)
from app.schemas.auth import WorkspaceMembershipRead
from app.services import admin_service

router = APIRouter(
    prefix="/admin", dependencies=[Depends(require_auth_enabled)]
)

_MUTATE = [Depends(require_local_control)]


def _read(user: User, last_seen, memberships) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_seen_at=last_seen,
        memberships=[
            WorkspaceMembershipRead(workspace_id=m.workspace_id, role=m.role)
            for m in memberships
        ],
    )


def _get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.get("/users", response_model=list[AdminUserRead])
def list_users(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_server_admin),
) -> list[AdminUserRead]:
    return [
        _read(u, seen, members)
        for u, seen, members in admin_service.list_users(session)
    ]


@router.post(
    "/users",
    response_model=AdminUserCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=_MUTATE,
)
def create_user(
    data: AdminUserCreate,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_server_admin),
) -> AdminUserCreated:
    try:
        user, temp = admin_service.create_user(session, data.email, data.display_name)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AdminUserCreated(user=_read(user, None, []), temp_password=temp)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminPasswordReset,
    dependencies=_MUTATE,
)
def reset_password(
    user_id: str,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_server_admin),
) -> AdminPasswordReset:
    user = _get_user(session, user_id)
    try:
        temp = admin_service.reset_password(session, user)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AdminPasswordReset(temp_password=temp)


@router.post(
    "/users/{user_id}/deactivate", response_model=AdminUserRead, dependencies=_MUTATE
)
def deactivate(
    user_id: str,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_server_admin),
) -> AdminUserRead:
    user = _get_user(session, user_id)
    try:
        user = admin_service.set_active(session, user, active=False)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _read(user, None, [])


@router.post(
    "/users/{user_id}/reactivate", response_model=AdminUserRead, dependencies=_MUTATE
)
def reactivate(
    user_id: str,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_server_admin),
) -> AdminUserRead:
    user = _get_user(session, user_id)
    user = admin_service.set_active(session, user, active=True)
    return _read(user, None, [])


@router.patch("/users/{user_id}", response_model=AdminUserRead, dependencies=_MUTATE)
def patch_user(
    user_id: str,
    data: AdminUserPatch,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_server_admin),
) -> AdminUserRead:
    user = _get_user(session, user_id)
    try:
        user = admin_service.set_admin(session, user, data.is_admin)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _read(user, None, [])
