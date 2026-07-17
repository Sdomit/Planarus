"""CalendarConnection persistence: encrypt tokens in, decrypt on demand, refresh
when expired (Phase 15.12b)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.core import token_crypto
from app.core.utils import new_id, now_utc
from app.models.calendar_connection import CalendarConnection
from app.models.project import Project
from app.services.audit_service import create_audit_event
from app.services.calendar_sync import CalendarBackend, CalendarTokens


def list_connections(session: Session, project_id: str) -> list[CalendarConnection]:
    return list(session.exec(
        select(CalendarConnection)
        .where(CalendarConnection.project_id == project_id)
        .order_by(CalendarConnection.created_at)
    ).all())


def get_connection(session: Session, connection_id: str) -> Optional[CalendarConnection]:
    return session.get(CalendarConnection, connection_id)


def create_connection(
    session: Session, project_id: str, provider: str, tokens: CalendarTokens
) -> CalendarConnection:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    now = now_utc()
    conn = CalendarConnection(
        id=new_id("con"),
        project_id=project_id,
        provider=provider,
        account_email=tokens.email,
        access_token_enc=token_crypto.encrypt(tokens.access_token),
        refresh_token_enc=token_crypto.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        token_expiry=tokens.expiry,
        scope=tokens.scope,
        status="connected",
        created_at=now,
        updated_at=now,
    )
    session.add(conn)
    session.flush()
    create_audit_event(
        session, event_type="create", actor_type="human",
        entity_type="calendar_connection", entity_id=conn.id, project_id=project_id,
    )
    session.commit()
    session.refresh(conn)
    return conn


def delete_connection(session: Session, connection_id: str) -> bool:
    conn = session.get(CalendarConnection, connection_id)
    if conn is None:
        return False
    project_id = conn.project_id
    session.delete(conn)
    create_audit_event(
        session, event_type="delete", actor_type="human",
        entity_type="calendar_connection", entity_id=connection_id, project_id=project_id,
    )
    session.commit()
    return True


def set_status(session: Session, conn: CalendarConnection, status: str) -> None:
    conn.status = status
    conn.updated_at = now_utc()
    session.add(conn)
    session.commit()


def _expired(expiry: Optional[str]) -> bool:
    if not expiry:
        return False  # no expiry recorded → assume the access token is still good
    try:
        return datetime.fromisoformat(expiry) <= datetime.fromisoformat(now_utc())
    except ValueError:
        return True


def valid_access_token(
    session: Session, backend: CalendarBackend, conn: CalendarConnection
) -> str:
    """Return a usable access token, refreshing (and re-encrypting) if expired."""
    if not _expired(conn.token_expiry):
        return token_crypto.decrypt(conn.access_token_enc)
    if not conn.refresh_token_enc:
        raise RuntimeError("access token expired and no refresh token is stored")
    refreshed = backend.refresh(token_crypto.decrypt(conn.refresh_token_enc))
    conn.access_token_enc = token_crypto.encrypt(refreshed.access_token)
    if refreshed.refresh_token:
        conn.refresh_token_enc = token_crypto.encrypt(refreshed.refresh_token)
    conn.token_expiry = refreshed.expiry
    conn.updated_at = now_utc()
    session.add(conn)
    session.commit()
    return refreshed.access_token
