"""ApiClient management service (Phase 7C1): create / list / revoke.

All proposal/read power flows from the credential booleans; this service only
issues, lists, and revokes credentials. It validates the explicit project scope
(non-empty, unique, ≤50, every id belonging to the workspace), generates the key
(raw key returned ONCE), stores only the Argon2id verifier, and writes metadata-
only audit events (never the raw key). Revocation is one-way (no re-enable).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc, now_utc_plus_hours
from app.models.api_client import ApiClient
from app.models.project import Project
from app.models.workspace import Workspace
from app.schemas.api_client import ApiClientCreate, ApiClientRead
from app.services import api_credentials
from app.services.audit_service import create_audit_event

MAX_PROJECT_IDS = 50
DEFAULT_EXPIRY_DAYS = 90
MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 365


def create_client(session: Session, payload: ApiClientCreate) -> tuple[ApiClient, str]:
    """Issue a new ApiClient. Returns (client, raw_key). Raises LookupError/ValueError."""
    if session.get(Workspace, payload.workspace_id) is None:
        raise LookupError("workspace not found")

    if not (payload.can_read or payload.can_propose):
        raise ValueError("at least one of can_read or can_propose must be true")

    project_ids = list(payload.project_ids)
    if not project_ids:
        raise ValueError("at least one project must be selected")
    if len(project_ids) != len(set(project_ids)):
        raise ValueError("project_ids must be unique")
    if len(project_ids) > MAX_PROJECT_IDS:
        raise ValueError(f"a key may scope at most {MAX_PROJECT_IDS} projects")
    for pid in project_ids:
        project = session.get(Project, pid)
        if project is None or project.workspace_id != payload.workspace_id:
            raise ValueError("every selected project must belong to the workspace")

    days = payload.expires_in_days if payload.expires_in_days is not None else DEFAULT_EXPIRY_DAYS
    if not (MIN_EXPIRY_DAYS <= days <= MAX_EXPIRY_DAYS):
        raise ValueError("expiry must be between 1 and 365 days")

    key_id, secret, full_key = api_credentials.generate_key()
    now = now_utc()
    client = ApiClient(
        id=new_id("apc"),
        workspace_id=payload.workspace_id,
        key_id=key_id,
        secret_hash=api_credentials.hash_secret(secret),
        label=(payload.label.strip()[:200] or "client"),
        can_read=bool(payload.can_read),
        can_propose=bool(payload.can_propose),
        project_ids_json=json.dumps(project_ids),
        enabled=True,
        created_at=now,
        expires_at=now_utc_plus_hours(days * 24),
    )
    session.add(client)
    # Audit metadata only — never the raw key, secret, or verifier.
    create_audit_event(
        session,
        event_type="api_client_created",
        actor_type="human",
        entity_type="api_client",
        entity_id=client.id,
        workspace_id=client.workspace_id,
        payload_json=json.dumps(
            {
                "key_id": key_id,
                "can_read": client.can_read,
                "can_propose": client.can_propose,
                "project_count": len(project_ids),
                "expires_at": client.expires_at,
            }
        ),
    )
    session.commit()
    session.refresh(client)
    return client, full_key


def list_clients(session: Session, workspace_id: Optional[str] = None) -> list[ApiClient]:
    stmt = select(ApiClient)
    if workspace_id:
        stmt = stmt.where(ApiClient.workspace_id == workspace_id)
    stmt = stmt.order_by(ApiClient.created_at.desc(), ApiClient.id)
    return list(session.exec(stmt).all())


def get_client(session: Session, client_id: str) -> Optional[ApiClient]:
    return session.get(ApiClient, client_id)


def revoke_client(session: Session, client_id: str) -> ApiClient:
    """Revoke a client (one-way; takes effect on the next external request)."""
    client = session.get(ApiClient, client_id)
    if client is None:
        raise LookupError("api client not found")
    if client.revoked_at is None:
        client.revoked_at = now_utc()
        client.enabled = False
        session.add(client)
        create_audit_event(
            session,
            event_type="api_client_revoked",
            actor_type="human",
            entity_type="api_client",
            entity_id=client.id,
            workspace_id=client.workspace_id,
            payload_json=json.dumps({"key_id": client.key_id}),
        )
        session.commit()
        session.refresh(client)
    return client


def to_read(client: ApiClient) -> ApiClientRead:
    """Safe serializer — never exposes secret_hash or the raw key."""
    try:
        project_ids = json.loads(client.project_ids_json)
    except (json.JSONDecodeError, TypeError):
        project_ids = []
    return ApiClientRead(
        id=client.id,
        workspace_id=client.workspace_id,
        key_id=client.key_id,
        label=client.label,
        can_read=client.can_read,
        can_propose=client.can_propose,
        project_ids=[p for p in project_ids if isinstance(p, str)],
        enabled=client.enabled,
        created_at=client.created_at,
        expires_at=client.expires_at,
        last_used_at=client.last_used_at,
        revoked_at=client.revoked_at,
    )
