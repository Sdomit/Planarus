"""Account-lifecycle operations for server admins (Phase 16.1, D29/D34).

Pure data operations, mirroring ``auth_service``'s conventions: duplicate or
impossible writes raise ``ConflictError``; "not found" is ``None`` for the
endpoint to translate. Accounts are never hard-deleted (D34) — deactivation is
the terminal state, so audit rows and ``decided_by`` keep resolving forever.

Every mutation writes an ``AuditEvent`` whose ``actor_id`` comes from the
request-scoped actor context (P16.0) — i.e. the acting admin.
"""
import json
import secrets
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings as env
from app.core.exceptions import ConflictError
from app.core.utils import new_id, now_utc
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.user_session import UserSession
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.services import auth_service
from app.services.api_credentials import hash_secret
from app.services.audit_service import create_audit_event


def _audit(session: Session, user: User, op: str) -> None:
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="user",
        entity_id=user.id,
        payload_json=json.dumps({"op": op}),
    )


def _temp_password() -> str:
    # 16 url-safe chars — comfortably past the 10-char policy minimum.
    return secrets.token_urlsafe(12)


def _require_password_provider() -> None:
    """Temp passwords are useless if nobody can sign in with them."""
    if not env.auth_password_enabled:
        raise ConflictError("the password provider is disabled on this server")


def _password_identity(session: Session, user_id: str) -> Optional[UserIdentity]:
    return session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == auth_service.PASSWORD_PROVIDER,
            UserIdentity.user_id == user_id,
        )
    ).first()


def _lock_admin_set(session: Session, user_id: str) -> None:
    """Serialize every operation that can change the active-admin count (#114).

    "At least one active admin" cannot be written as a portable constraint, so it
    is held by serializing the writers instead. This locks the target row *and*
    every active admin in one ordered statement: ordered so two transactions
    always take the same rows in the same order (no deadlock), and one statement
    so there is no window between the two sets.

    On PostgreSQL this is a real ``FOR UPDATE`` — the second self-demotion blocks
    until the first commits and then re-reads a world where it is the last admin.
    On SQLite the clause is a no-op (the dialect has no row locks); there the
    guarantee comes from the conditional UPDATE below, which SQLite evaluates
    atomically under its single writer lock. Both engines need both halves.
    """
    session.exec(
        select(User)
        .where(
            or_(
                User.id == user_id,
                and_(
                    User.is_admin == True,  # noqa: E712
                    User.is_active == True,  # noqa: E712
                ),
            )
        )
        .order_by(User.id)
        .with_for_update()
    ).all()


def _demote_or_deactivate(session: Session, user_id: str, *, column, value) -> bool:
    """Flip ``column`` on an admin only while another active admin survives.

    The invariant travels *inside* the UPDATE as an EXISTS, so the check and the
    write are one statement and cannot be interleaved. Returns False (rowcount 0)
    when the account is the last active admin — or when a racing transaction has
    already changed it, which is the same answer for the caller.
    """
    other = select(User.id).where(
        User.is_admin == True,  # noqa: E712
        User.is_active == True,  # noqa: E712
        User.id != user_id,
    )
    result = session.execute(
        sa_update(User)
        .where(User.id == user_id, other.exists())
        .values(**{column: value, "updated_at": now_utc()})
    )
    return result.rowcount == 1


def list_users(session: Session) -> list[tuple[User, Optional[str], list[WorkspaceMember]]]:
    """Roster: every account with its last-seen instant and memberships."""
    users = list(session.exec(select(User).order_by(User.created_at)).all())
    seen: dict[str, Optional[str]] = dict(
        session.exec(
            select(UserSession.user_id, func.max(UserSession.last_seen_at)).group_by(
                UserSession.user_id
            )
        ).all()
    )
    members: dict[str, list[WorkspaceMember]] = {}
    for m in session.exec(select(WorkspaceMember)).all():
        members.setdefault(m.user_id, []).append(m)
    return [(u, seen.get(u.id), members.get(u.id, [])) for u in users]


def list_unclaimed_workspaces(session: Session) -> list[Workspace]:
    """Workspaces with zero members — invisible to /workspaces (D30's own
    membership scoping) and therefore invisible to their own admin.

    Real case, not a hypothetical: turning auth on for the first time on a
    server that already had local-mode data leaves every existing workspace
    ownerless, and ``members.py``'s own bootstrap rule ("the first member must
    be yourself, added as owner") has no UI that ever shows the workspace to
    claim. Admin-only: naming an empty workspace is a narrow, deliberate leak
    to the one role that can already list every account on the server.
    """
    owned = set(session.exec(select(WorkspaceMember.workspace_id)).all())
    workspaces = session.exec(select(Workspace).order_by(Workspace.created_at)).all()
    return [w for w in workspaces if w.id not in owned]


def create_user(
    session: Session, email: str, display_name: Optional[str]
) -> tuple[User, str]:
    """Create an account with a one-time temp password (must-change on sign-in).

    Create-only, same anti-takeover rule as self-registration: an email that
    already has an account raises ``ConflictError``. No session is opened and
    no workspace membership is granted — an owner grants roles via the members
    API; admin authority never reaches into workspaces (D29).
    """
    _require_password_provider()
    norm = email.strip().lower()
    if session.exec(select(User).where(User.email == norm)).first() is not None:
        raise ConflictError("an account with this email already exists")
    now = now_utc()
    user = User(
        id=new_id("usr"),
        email=norm,
        display_name=(display_name or norm.split("@")[0]).strip()[:200] or norm,
        is_admin=False,  # an admin exists (the caller); never bootstrap here
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("an account with this email already exists") from exc
    temp = _temp_password()
    session.add(
        UserIdentity(
            id=new_id("uid"),
            user_id=user.id,
            provider=auth_service.PASSWORD_PROVIDER,
            provider_subject=norm,
            password_hash=hash_secret(temp),
            password_must_change=True,
            created_at=now,
        )
    )
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="user",
        entity_id=user.id,
        payload_json=json.dumps({"op": "admin_create"}),
    )
    session.commit()
    session.refresh(user)
    return user, temp


def reset_password(session: Session, user: User) -> str:
    """Issue a new one-time temp password and revoke every session.

    ``ConflictError`` for accounts without a password identity — an admin reset
    must never attach a FIRST password to an OAuth/dev account (the same
    account-takeover rule register enforces).
    """
    _require_password_provider()
    identity = _password_identity(session, user.id)
    if identity is None:
        raise ConflictError("this account has no password login")
    temp = _temp_password()
    identity.password_hash = hash_secret(temp)
    identity.password_must_change = True
    session.add(identity)
    auth_service.revoke_all_sessions(session, user.id)
    _audit(session, user, "reset_password")
    session.commit()
    return temp


def set_active(session: Session, user: User, active: bool) -> User:
    """Deactivate (revoking every session) or reactivate an account (D34).

    Deactivating an admin goes through the serialized last-admin path (#114);
    everything else is an ordinary write.
    """
    if not active and user.is_admin:
        _lock_admin_set(session, user.id)
        if not _demote_or_deactivate(session, user.id, column="is_active", value=False):
            session.rollback()
            raise ConflictError("cannot deactivate the last active admin")
        session.refresh(user)
    else:
        user.is_active = active
        user.updated_at = now_utc()
        session.add(user)
    if not active:
        auth_service.revoke_all_sessions(session, user.id)
    _audit(session, user, "deactivate" if not active else "reactivate")
    session.commit()
    session.refresh(user)
    return user


def set_admin(session: Session, user: User, is_admin: bool) -> User:
    """Grant or revoke the server-admin flag, guarding the last active admin."""
    if not is_admin and user.is_admin:
        _lock_admin_set(session, user.id)
        if not _demote_or_deactivate(session, user.id, column="is_admin", value=False):
            session.rollback()
            raise ConflictError("cannot demote the last active admin")
        session.refresh(user)
    else:
        user.is_admin = is_admin
        user.updated_at = now_utc()
        session.add(user)
    _audit(session, user, "admin_granted" if is_admin else "admin_revoked")
    session.commit()
    session.refresh(user)
    return user
