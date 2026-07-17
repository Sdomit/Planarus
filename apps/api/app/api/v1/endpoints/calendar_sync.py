"""External calendar sync endpoints (Phase 15.12b–d).

Every route that touches a provider is gated: `get_backend()` returns None unless
the encryption key AND that provider's client id are configured, so an unconfigured
install answers 404 and no token path is reachable. Connection reads never include
tokens. Connect uses a signed state to carry the flow context (no session).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.calendar_connection import CalendarConnectionRead, SyncResult
from app.services import calendar_connection_service as conns
from app.services import calendar_sync, calendar_sync_service

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


@router.get("/calendar-sync/{provider}/connect")
def connect(
    provider: str,
    project_id: str = Query(...),
    redirect_uri: str = Query(..., description="OAuth callback URL registered with the provider"),
    session: Session = Depends(get_session),
) -> dict:
    backend = _require_backend(provider)
    state = calendar_sync.make_state(
        {"project_id": project_id, "provider": provider, "redirect_uri": redirect_uri}
    )
    return {"authorize_url": backend.authorize_url(state, redirect_uri)}


@router.get("/calendar-sync/{provider}/callback")
def callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    backend = _require_backend(provider)
    ctx = calendar_sync.verify_state(state)
    if ctx is None or ctx.get("provider") != provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state")
    tokens = backend.exchange_code(code, ctx["redirect_uri"])
    try:
        conns.create_connection(session, ctx["project_id"], provider, tokens)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return HTMLResponse(content=_DONE_HTML)


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
