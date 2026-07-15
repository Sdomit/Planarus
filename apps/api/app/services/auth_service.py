"""Identity, session, and membership operations (Phase 10.1, hosted mode).

Pure data operations over the identity tables. Authorization (who may call what)
is enforced at the HTTP boundary in ``app/api/v1/endpoints`` using the helpers in
``app/core/auth_deps.py``; this module stays free of FastAPI/HTTP types, matching
the other services. Duplicate writes raise ``ConflictError``; "not found" is
returned as ``None`` for the endpoint to translate.
"""
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.utils import new_id, now_utc, now_utc_plus_hours, sha256_hex
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.user_session import UserSession
from app.models.workspace_member import WorkspaceMember
from app.services.audit_service import create_audit_event

SESSION_COOKIE = "approvo_session"


# --- sessions -----------------------------------------------------------------
def _hash_token(raw_token: str) -> str:
    return sha256_hex(raw_token)


def create_session(session: Session, user_id: str) -> str:
    """Create a server-side session and return the raw opaque token (shown once).

    Only the SHA-256 of the token is persisted; the raw value is never stored.
    """
    raw_token = new_id("sess") + "." + new_id("tok")
    row = UserSession(
        id=new_id("usess"),
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        created_at=now_utc(),
        expires_at=now_utc_plus_hours(settings.auth_session_ttl_hours),
    )
    session.add(row)
    return raw_token


def resolve_user(session: Session, raw_token: Optional[str]) -> Optional[User]:
    """Return the live user for a session token, or None if absent/invalid/expired.

    Touches ``last_seen_at`` on a successful resolve. Never raises for a bad token.
    """
    if not raw_token:
        return None
    row = session.exec(
        select(UserSession).where(UserSession.token_hash == _hash_token(raw_token))
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    # ISO-8601 UTC strings share one format → correct lexicographic comparison.
    if row.expires_at <= now_utc():
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    row.last_seen_at = now_utc()
    session.add(row)
    session.commit()
    return user


def revoke_session(session: Session, raw_token: Optional[str]) -> None:
    """Idempotently revoke a session by its raw token (no-op if unknown)."""
    if not raw_token:
        return
    row = session.exec(
        select(UserSession).where(UserSession.token_hash == _hash_token(raw_token))
    ).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = now_utc()
        session.add(row)
        session.commit()


# --- users / dev-login --------------------------------------------------------
def _normalize_email(email: str) -> str:
    return email.strip().lower()


def dev_login(
    session: Session, email: str, display_name: Optional[str]
) -> tuple[User, str]:
    """Password-less get-or-create login via the ``dev`` provider.

    Doubly-gated at the endpoint (auth + dev-login flags). Finds the user by email
    or creates one, ensures a ``dev`` identity is linked, and returns the user plus
    a fresh raw session token.
    """
    norm = _normalize_email(email)
    user = session.exec(select(User).where(User.email == norm)).first()
    if user is None:
        now = now_utc()
        user = User(
            id=new_id("usr"),
            email=norm,
            display_name=(display_name or norm.split("@")[0]).strip()[:200] or norm,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        create_audit_event(
            session,
            event_type="create",
            actor_type="human",
            entity_type="user",
            entity_id=user.id,
        )
    identity = session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == "dev",
            UserIdentity.provider_subject == norm,
        )
    ).first()
    if identity is None:
        session.add(
            UserIdentity(
                id=new_id("uid"),
                user_id=user.id,
                provider="dev",
                provider_subject=norm,
                created_at=now_utc(),
            )
        )
    raw_token = create_session(session, user.id)
    session.commit()
    session.refresh(user)
    return user, raw_token


# --- membership ---------------------------------------------------------------
def role_in_workspace(
    session: Session, workspace_id: str, user_id: str
) -> Optional[str]:
    row = session.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()
    return row.role if row else None


def list_members(session: Session, workspace_id: str) -> list[WorkspaceMember]:
    return list(
        session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id
            )
        ).all()
    )


def count_owners(session: Session, workspace_id: str) -> int:
    return len(
        [m for m in list_members(session, workspace_id) if m.role == "owner"]
    )


def user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(
        select(User).where(User.email == _normalize_email(email))
    ).first()


def add_member(
    session: Session, workspace_id: str, user_id: str, role: str
) -> WorkspaceMember:
    """Add a workspace member. Raises ConflictError if already a member."""
    now = now_utc()
    member = WorkspaceMember(
        id=new_id("wsm"),
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        created_at=now,
        updated_at=now,
    )
    session.add(member)
    try:
        session.flush()
    except IntegrityError as exc:  # unique(workspace_id, user_id) violation
        session.rollback()
        raise ConflictError("user is already a member of this workspace") from exc
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="workspace_member",
        entity_id=member.id,
        workspace_id=workspace_id,
    )
    session.commit()
    session.refresh(member)
    return member


def get_member(
    session: Session, workspace_id: str, user_id: str
) -> Optional[WorkspaceMember]:
    return session.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()


def set_member_role(
    session: Session, member: WorkspaceMember, role: str
) -> WorkspaceMember:
    member.role = role
    member.updated_at = now_utc()
    session.add(member)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="workspace_member",
        entity_id=member.id,
        workspace_id=member.workspace_id,
    )
    session.commit()
    session.refresh(member)
    return member


def remove_member(session: Session, member: WorkspaceMember) -> None:
    workspace_id, member_id = member.workspace_id, member.id
    session.delete(member)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="workspace_member",
        entity_id=member_id,
        workspace_id=workspace_id,
    )
    session.commit()
