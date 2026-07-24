"""Hosted-mode auth endpoints (Phase 10.1).

Mounted always but gated by ``require_auth_enabled`` — when auth is disabled the
whole surface 404s and the app is the local single-user tool. No tenant
enforcement on domain routes yet (P10.2).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlmodel import Session, select

from app.core.auth_deps import get_current_user, require_auth_enabled
from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.rate_limit import RateLimiter
from app.db.session import get_session
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import (
    AuthMeRead,
    DevLoginRequest,
    PasswordChangeRequest,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    UserRead,
    WorkspaceMembershipRead,
)
from app.services import auth_service, oauth, settings_service

router = APIRouter(dependencies=[Depends(require_auth_enabled)])

# P11.1: per-email fixed-window throttle on password logins, reusing the 7C1
# limiter (its read bucket serves as the attempt bucket). In-process by design,
# like the rest of rate_limit.py; Argon2id already makes each attempt expensive.
# ponytail: 10 attempts/min/email, resets on restart; failure-only or IP+email
# keying only if real abuse shows up.
_pw_limiter = RateLimiter(read_per_min=10)


def _cookie_secure() -> bool:
    """Whether auth cookies may carry the ``Secure`` attribute.

    Relaxed when the dev-login provider is on (local/tests over http), when LAN
    mode is on — D26 ratified plain HTTP on the LAN — or when auth is off
    entirely (the local single-user tool, always http://localhost). A Secure
    cookie over http:// is silently dropped by browsers, which would brick the
    flow that set it. A real hosted deployment gets Secure cookies.
    """
    return settings.auth_enabled and not (
        settings.auth_dev_login_enabled or settings.lan_mode_enabled
    )


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=auth_service.SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
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
        # P16.1: lets the web force the change-password screen for temp passwords.
        password_must_change=auth_service.password_must_change(session, user.id),
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


@router.get("/auth/status")
def auth_status(session: Session = Depends(get_session)) -> dict:
    """First-run probe for the sign-in screen: is this server still unclaimed?

    Unauthenticated by necessity — it is read before anyone can sign in — and
    only ever true before the first account exists (D29).

    Gated on the password provider too: the setup screen it drives is the
    register form, and with the provider off that form 404s. An OAuth-only or
    dev-login server answers false and gets the plain gate instead.
    """
    unclaimed = settings.auth_password_enabled and auth_service.needs_setup(session)
    return {"needs_setup": unclaimed}


# --- P11.1: local email+password provider (D25) --------------------------------
def _require_password_enabled() -> None:
    """404 the password surface unless its flag is on (dev-login precedent)."""
    if not settings.auth_password_enabled:
        raise HTTPException(status_code=404, detail="not found")


@router.post(
    "/auth/password/register",
    response_model=AuthMeRead,
    status_code=status.HTTP_201_CREATED,
)
def password_register(
    data: PasswordRegisterRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthMeRead:
    """Create a new account (create-only: 409 if the email exists — never links
    onto an existing account) and open a session. Workspace access still requires
    membership granted by an owner; a fresh account can see nothing.

    P16.1 (D30): a closed ``registration_open`` switch answers the same generic
    404 as a disabled provider — closed registration is indistinguishable from
    no password surface at all."""
    _require_password_enabled()
    if not settings_service.registration_open(session):
        raise HTTPException(status_code=404, detail="not found")
    try:
        user, raw_token = auth_service.register_password_user(
            session, data.email, data.password, data.display_name
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _set_session_cookie(response, raw_token)
    return _me(session, user)


@router.post("/auth/password/login", response_model=AuthMeRead)
def password_login(
    data: PasswordLoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthMeRead:
    _require_password_enabled()
    retry_after = _pw_limiter.check_read(data.email.strip().lower())
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="too many login attempts; try again shortly",
            headers={"Retry-After": str(int(retry_after))},
        )
    result = auth_service.login_with_password(session, data.email, data.password)
    if result is None:
        # One generic message for unknown email / wrong password / inactive.
        raise HTTPException(status_code=401, detail="invalid email or password")
    user, raw_token = result
    _set_session_cookie(response, raw_token)
    return _me(session, user)


@router.post("/auth/password/change", status_code=status.HTTP_204_NO_CONTENT)
def password_change(
    data: PasswordChangeRequest,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    """Rotate the caller's own password (requires the current one); every other
    session for the account is revoked, the caller's cookie survives."""
    _require_password_enabled()
    try:
        ok = auth_service.change_password(
            session,
            user,
            data.current_password,
            data.new_password,
            keep_raw_token=request.cookies.get(auth_service.SESSION_COOKIE),
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=400, detail="current password is incorrect")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


# --- P10.1b: real OAuth (Google/GitHub) ---------------------------------------
@router.get("/auth/oauth/providers")
def oauth_providers() -> dict:
    """Which OAuth providers are configured (have a client id set)."""
    return {"providers": oauth.available_providers()}


def _begin_oauth(
    session: Session,
    response: Response,
    *,
    kind: str,
    provider: str,
    redirect_uri: str,
    user_id: str | None = None,
) -> dict:
    """Open a one-time transaction, bind it to this browser, and hand back the
    provider's authorization URL (#113)."""
    prov = oauth.get_provider(provider)
    if prov is None:
        raise HTTPException(status_code=404, detail="unknown or unconfigured provider")
    if not oauth.is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(status_code=400, detail="redirect_uri is not allowlisted")
    oauth.purge_expired_transactions(session)
    state, binder = oauth.start_transaction(
        session, kind=kind, provider=provider, redirect_uri=redirect_uri, user_id=user_id
    )
    session.commit()
    set_binder_cookie(response, binder)
    return {"authorize_url": prov.authorize_url(state, redirect_uri)}


def set_binder_cookie(response: Response, binder: str) -> None:
    """The browser half of an OAuth transaction (#113).

    Scoped to ``/api/v1`` so both the login and the calendar callback see it, and
    to the transaction's own lifetime. ``samesite=lax`` is required, not
    cosmetic: the callback arrives as a top-level cross-site navigation from the
    provider, which ``strict`` would strip. ``secure`` follows the session
    cookie's rule so local/LAN plain HTTP still works.
    """
    response.set_cookie(
        key=oauth.BINDER_COOKIE,
        value=binder,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/api/v1",
        max_age=oauth.STATE_TTL_SECONDS,
    )


def clear_binder_cookie(response: Response) -> None:
    response.delete_cookie(oauth.BINDER_COOKIE, path="/api/v1")


@router.get("/auth/oauth/{provider}/start")
def oauth_start(
    provider: str,
    response: Response,
    redirect_uri: str = Query(..., description="the callback URL registered with the provider"),
    session: Session = Depends(get_session),
) -> dict:
    """Return the provider authorization URL to redirect the browser to, and set
    the binder cookie that ties the resulting callback to this browser. 404 if the
    provider isn't configured; 400 if the redirect_uri isn't allowlisted."""
    return _begin_oauth(
        session, response, kind="login", provider=provider, redirect_uri=redirect_uri
    )


@router.get("/auth/oauth/{provider}/link/start")
def oauth_link_start(
    provider: str,
    response: Response,
    redirect_uri: str = Query(..., description="the callback URL registered with the provider"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Begin linking another provider to the signed-in account (#113).

    The authenticated half of "no silent email-based linking": the transaction
    records who asked, and the callback only attaches the identity if the same
    account is still signed in.
    """
    return _begin_oauth(
        session,
        response,
        kind="link",
        provider=provider,
        redirect_uri=redirect_uri,
        user_id=user.id,
    )


@router.get("/auth/oauth/{provider}/callback", response_model=AuthMeRead)
def oauth_callback(
    request: Request,
    provider: str,
    response: Response,
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
) -> AuthMeRead:
    """Exchange the auth code and either open a session or link the identity.

    The transaction is claimed once, atomically, before the code is exchanged, so
    a replayed callback never reaches the provider at all.
    """
    prov = oauth.get_provider(provider)
    if prov is None:
        raise HTTPException(status_code=404, detail="unknown or unconfigured provider")
    binder = request.cookies.get(oauth.BINDER_COOKIE)
    txn = oauth.consume_transaction(
        session, state=state, binder=binder, kinds=("login", "link"), provider=provider
    )
    session.commit()
    if txn is None:
        raise HTTPException(status_code=400, detail="invalid, expired, or already-used state")
    linking = txn.kind == "link"
    clear_binder_cookie(response)

    identity = prov.exchange_code(code, txn.redirect_uri)
    if not identity.email:
        raise HTTPException(status_code=400, detail="provider did not return an email")
    if not identity.email_verified:
        raise HTTPException(
            status_code=400, detail="provider did not report a verified email"
        )

    if linking:
        # Re-authorize at the callback: the transaction's opener must still be the
        # signed-in user, so a link started in one account cannot land in another.
        current = auth_service.resolve_user(
            session, request.cookies.get(auth_service.SESSION_COOKIE)
        )
        if current is None or current.id != txn.user_id:
            raise HTTPException(status_code=403, detail="sign in again to link this provider")
        # A subject already linked elsewhere raises ConflictError → 409 via the
        # app-wide handler.
        auth_service.link_identity(
            session, current.id, identity.provider, identity.subject
        )
        return _me(session, current)

    user, raw_token = auth_service.login_with_identity(
        session, identity.provider, identity.subject, identity.email, identity.display_name
    )
    _set_session_cookie(response, raw_token)
    return _me(session, user)
