"""Two-way sync between local CalendarEvents and an external provider (15.12c/d).

Strategy (per the plan — "push first, then pull-back"):
  * PUSH  — every local event that has never synced (external_uid is null) and is
            non-recurring is created on the provider; we store its id + etag.
  * PULL  — the provider's events are upserted locally, keyed by external_uid;
            the provider wins on divergence (etag changed) and on deletion.

ponytail ceilings: recurring events are not pushed (plan defers recurrence);
edits to already-synced local events aren't pushed back yet — after the initial
push the provider side is authoritative on pull. Both are safe (never silently
overwrite the remote); lift when local-authoritative edits are needed.
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.calendar_connection import CalendarConnection
from app.models.calendar_event import CalendarEvent
from app.schemas.calendar_connection import SyncResult
from app.services import calendar_connection_service as conns
from app.services.calendar_sync import CalendarBackend, PushEvent, RemoteEvent, get_backend


def _push(session: Session, backend: CalendarBackend, access: str, conn: CalendarConnection) -> int:
    unsynced = session.exec(
        select(CalendarEvent).where(
            CalendarEvent.project_id == conn.project_id,
            CalendarEvent.external_uid.is_(None),  # type: ignore[union-attr]
            CalendarEvent.recurrence == "none",
        )
    ).all()
    pushed = 0
    for ev in unsynced:
        remote = backend.create_event(access, PushEvent(
            title=ev.title, start_at=ev.start_at, end_at=ev.end_at, all_day=ev.all_day,
        ))
        ev.external_uid = remote.external_uid
        ev.etag = remote.etag
        ev.updated_at = now_utc()
        session.add(ev)
        pushed += 1
    return pushed


def _apply_remote(session: Session, conn: CalendarConnection, r: RemoteEvent) -> None:
    existing = session.exec(
        select(CalendarEvent).where(
            CalendarEvent.project_id == conn.project_id,
            CalendarEvent.external_uid == r.external_uid,
        )
    ).first()
    if r.deleted:
        if existing:
            session.delete(existing)
        return
    if existing is None:
        now = now_utc()
        session.add(CalendarEvent(
            id=new_id("cal"), project_id=conn.project_id, title=r.title,
            start_at=r.start_at, end_at=r.end_at, all_day=r.all_day, status="confirmed",
            recurrence="none", external_uid=r.external_uid, etag=r.etag,
            created_at=now, updated_at=now,
        ))
    elif existing.etag != r.etag:  # provider changed it → provider wins
        existing.title, existing.start_at, existing.end_at, existing.all_day = (
            r.title, r.start_at, r.end_at, r.all_day
        )
        existing.etag = r.etag
        existing.updated_at = now_utc()
        session.add(existing)


def sync_connection(session: Session, connection_id: str) -> SyncResult:
    conn = conns.get_connection(session, connection_id)
    if conn is None:
        raise LookupError("connection not found")
    backend = get_backend(conn.provider)
    if backend is None:
        raise RuntimeError(f"provider '{conn.provider}' is not configured")

    try:
        access = conns.valid_access_token(session, backend, conn)
        pushed = _push(session, backend, access, conn)
        remotes, next_token = backend.list_events(access, conn.sync_token)
        for r in remotes:
            _apply_remote(session, conn, r)
        conn.sync_token = next_token
        conn.last_synced_at = now_utc()
        conn.status = "connected"
        conn.updated_at = now_utc()
        session.add(conn)
        session.commit()
    except Exception:
        conns.set_status(session, conn, "error")
        raise

    return SyncResult(
        connection_id=conn.id, pushed=pushed, pulled=len(remotes), status=conn.status
    )
