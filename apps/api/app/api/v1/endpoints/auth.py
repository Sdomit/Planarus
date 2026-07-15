"""Hosted-mode auth endpoints (Phase 10.1).

Mounted always but gated by ``require_auth_enabled`` — when auth is disabled the
whole surface 404s and the app is the local single-user tool. No tenant
enforcement on domain routes yet (P10.2).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.core.auth_deps import get_current_user, require_auth_enabled
from app.core.config import settings
from app.db.session import get_session
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import (
    AuthMeRead,
    DevLoginRequest,
    UserRead,
    WorkspaceMembershipRead,
)
from app.services import auth_service

router = APIRouter(dependencies=[Depends(require_auth_enabled)])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    # `secure` is relaxed only when the dev-login provider is on (local/tests over
    # http); a real hosted deployment (dev-login off) always gets Secure cookies.
    response.set_cookie(
        key=auth_service.SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=not settings.auth_dev_login_enabled,
        path="/",
    )


def _me(session: Session, user: User) -> AuthMeRead:
    memberships = session.exec(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    ).all()
    return AuthMeRead(
        user=UserRead.model_validate(user),
        memberships=[
            WorkspaceMembershipRead(workspace_id=m.workspace_id, role=m.role)
            for m in memberships
        ],
    )


@router.post("/auth/dev-login", response_model=AuthMeRead)
def dev_login(
    data: DevLoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthMeRead:
    if not settings.auth_dev_login_enabled:
        raise HTTPException(status_code=404, detail="not found")
    user, raw_token = auth_service.dev_login(session, data.email, data.display_name)
    _set_session_cookie(response, raw_token)
    return _me(session, user)


@router.get("/auth/me", response_model=AuthMeRead)
def me(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AuthMeRead:
    return _me(session, user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> Response:
    auth_service.revoke_session(
        session, request.cookies.get(auth_service.SESSION_COOKIE)
    )
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
