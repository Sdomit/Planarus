"""External calendar sync endpoints (Phase 15.12b–d).

Every route that touches a provider is gated: `get_backend()` returns None unless
the encryption key AND that provider's client id are configured, so an unconfigured
install answers 404 and no token path is reachable. Connection reads never include
tokens.

Connect/callback share the login flow's server-side one-time OAuth transactions
(#113). The callback carries no `project_id`, so the registry-driven
`tenant_guard` never matches it — it therefore re-authorizes explicitly here:
same browser (binder cookie), same signed-in user that opened the transaction,
and that user still holding a write role on the project the tokens would attach
to. Without those checks a callback could attach a provider's calendar tokens to
another tenant's project.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.v1.endpoints.auth import clear_binder_cookie, set_binder_cookie
from app.core.config import settings
from app.core.tenant import WRITE_ROLES, require_project_access
from app.db.session import get_session
from app.models.project import Project
from app.schemas.calendar_connection import CalendarConnectionRead, SyncResult
from app.services import auth_service, calendar_sync, calendar_sync_service, oauth
from app.services import calendar_connection_service as conns

router = APIRouter()

_DONE_HTML = (
    "<!doctype html><meta charset=utf-8><title>Connected</title>"
    "<body style='font-family:sans-serif;padding:2rem'>"
    "<p>Calendar connected. You can close this window.</p>"
    "<script>try{window.close()}catch(e){}</script>"
)


def _require_backend(provider: str):
    backend = calendar_sync.get_backend(provider)
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar sync provider '{provider}' is not configured",
        )
    return backend


@router.get("/calendar-sync/providers")
def list_providers() -> dict:
    """Which providers are configured (empty when sync is off)."""
    return {"providers": calendar_sync.available_providers()}


@router.get(
    "/projects/{project_id}/calendar-connections",
    response_model=list[CalendarConnectionRead],
)
def list_connections(project_id: str, session: Session = Depends(get_session)):
    return conns.list_connections(session, project_id)


def _require_project_write(session: Session, project_id: str, user) -> None:
    """403/404 unless the caller may write this project. No-op when auth is off."""
    if not settings.auth_enabled:
        return
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    require_project_access(session, project, user, *WRITE_ROLES)


@router.get("/calendar-sync/{provider}/connect")
def connect(
    request: Request,
    response: Response,
    provider: str,
    project_id: str = Query(...),
    redirect_uri: str = Query(..., description="OAuth callback URL registered with the provider"),
    session: Session = Depends(get_session),
) -> dict:
    backend = _require_backend(provider)
    # tenant_guard already matched `project_id`, but this is a GET, so it only
    # enforced the READ roles — connecting a calendar is a write.
    user = auth_service.resolve_user(
        session, request.cookies.get(auth_service.SESSION_COOKIE)
    )
    _require_project_write(session, project_id, user)
    if not oauth.is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri is not allowlisted"
        )
    oauth.purge_expired_transactions(session)
    state, binder = oauth.start_transaction(
        session,
        kind="calendar",
        provider=provider,
        redirect_uri=redirect_uri,
        user_id=user.id if user is not None else None,
        project_id=project_id,
    )
    session.commit()
    set_binder_cookie(response, binder)
    return {"authorize_url": backend.authorize_url(state, redirect_uri)}


@router.get("/calendar-sync/{provider}/callback")
def callback(
    request: Request,
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    backend = _require_backend(provider)
    txn = oauth.consume_transaction(
        session,
        state=state,
        binder=request.cookies.get(oauth.BINDER_COOKIE),
        kinds=("calendar",),
        provider=provider,
    )
    session.commit()
    if txn is None or not txn.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already-used state",
        )
    project_id, redirect_uri, opener_id = txn.project_id, txn.redirect_uri, txn.user_id
    # Re-authorize at the callback (#113): the guard cannot see this route.
    if settings.auth_enabled:
        user = auth_service.resolve_user(
            session, request.cookies.get(auth_service.SESSION_COOKIE)
        )
        if user is None or user.id != opener_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sign in as the account that started this connection",
            )
        _require_project_write(session, project_id, user)
    tokens = backend.exchange_code(code, redirect_uri)
    try:
        conns.create_connection(session, project_id, provider, tokens)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    resp = HTMLResponse(content=_DONE_HTML)
    clear_binder_cookie(resp)
    return resp


@router.delete("/calendar-connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(connection_id: str, session: Session = Depends(get_session)) -> None:
    if not conns.delete_connection(session, connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")


@router.post("/calendar-connections/{connection_id}/sync", response_model=SyncResult)
def sync_now(connection_id: str, session: Session = Depends(get_session)) -> SyncResult:
    try:
        return calendar_sync_service.sync_connection(session, connection_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
