"""Local-human-only ApiClient management endpoints (Phase 7C1).

Guarded by the Phase 7A ``require_local_control`` dependency (in-memory local
control token + Origin allowlist) — NOT by an external API key. External clients
can never reach these routes. The raw key is returned exactly once (create) and
never appears in list/revoke responses, audit, or logs. Revoke is one-way; there
is no re-enable, delete, or bulk-issue endpoint.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.security import require_local_control
from app.db.session import get_session
from app.schemas.api_client import ApiClientCreate, ApiClientCreated, ApiClientRead
from app.services import api_client_service

router = APIRouter()


@router.get(
    "/api-clients",
    response_model=list[ApiClientRead],
    dependencies=[Depends(require_local_control)],
)
def list_api_clients(
    workspace_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[ApiClientRead]:
    return [
        api_client_service.to_read(c)
        for c in api_client_service.list_clients(session, workspace_id)
    ]


@router.post(
    "/api-clients",
    response_model=ApiClientCreated,
    status_code=201,
    dependencies=[Depends(require_local_control)],
)
def create_api_client(
    payload: ApiClientCreate,
    session: Session = Depends(get_session),
) -> ApiClientCreated:
    try:
        client, raw_key = api_client_service.create_client(session, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return ApiClientCreated(client=api_client_service.to_read(client), api_key=raw_key)


@router.post(
    "/api-clients/{client_id}/revoke",
    response_model=ApiClientRead,
    dependencies=[Depends(require_local_control)],
)
def revoke_api_client(
    client_id: str,
    session: Session = Depends(get_session),
) -> ApiClientRead:
    try:
        client = api_client_service.revoke_client(session, client_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return api_client_service.to_read(client)
