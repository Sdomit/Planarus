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
from app.services.api_credentials import dummy_verify, hash_secret, verify_secret
from app.services.audit_service import create_audit_event

SESSION_COOKIE = "planarus_session"


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


def revoke_all_sessions(session: Session, user_id: str) -> None:
    """Revoke every live session for a user (admin reset/deactivate). Caller
    commits."""
    now = now_utc()
    rows = session.exec(
        select(UserSession).where(UserSession.user_id == user_id)
    ).all()
    for row in rows:
        if row.revoked_at is None:
            row.revoked_at = now
            session.add(row)


def password_must_change(session: Session, user_id: str) -> bool:
    """Whether the user's password identity carries the admin-issued
    must-change flag (P16.1, D29). False for accounts without a password login.

    ponytail: one indexed lookup per authenticated request in team mode; stamp
    it into the session row if it ever shows up in a profile.
    """
    identity = session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == PASSWORD_PROVIDER,
            UserIdentity.user_id == user_id,
        )
    ).first()
    return bool(identity is not None and identity.password_must_change)


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


def _bootstrap_admin(session: Session) -> bool:
    """D29: the very first account on a server becomes its admin.

    ponytail: unguarded existence check — two racing first registrations could
    both win admin; LAN-scale accepted, and the last-active-admin guard keeps
    the system recoverable either way.
    """
    return session.exec(select(User.id).limit(1)).first() is None


def needs_setup(session: Session) -> bool:
    """Whether this server is still unclaimed — the next account becomes admin.

    Public read of the same D29 check, for the first-run sign-in screen. It does
    leak "no accounts yet", unlike D30's deliberately opaque closed-registration
    404, but only until someone registers: after that it is false forever.
    """
    return _bootstrap_admin(session)


def login_with_identity(
    session: Session,
    provider: str,
    subject: str,
    email: str,
    display_name: Optional[str],
) -> tuple[User, str]:
    """Get-or-create a user for a ``(provider, subject)`` identity and open a session.

    The account key is the normalized email — a user who already exists (e.g. via a
    different provider) gets the new identity linked rather than a duplicate account.
    Shared by the dev provider and the real OAuth providers (P10.1b). Returns the
    user plus a fresh raw session token.
    """
    norm = _normalize_email(email)
    user = session.exec(select(User).where(User.email == norm)).first()
    if user is None:
        now = now_utc()
        user = User(
            id=new_id("usr"),
            email=norm,
            display_name=(display_name or norm.split("@")[0]).strip()[:200] or norm,
            is_admin=_bootstrap_admin(session),
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
            UserIdentity.provider == provider,
            UserIdentity.provider_subject == subject,
        )
    ).first()
    if identity is None:
        session.add(
            UserIdentity(
                id=new_id("uid"),
                user_id=user.id,
                provider=provider,
                provider_subject=subject,
                created_at=now_utc(),
            )
        )
    raw_token = create_session(session, user.id)
    session.commit()
    session.refresh(user)
    return user, raw_token


def dev_login(
    session: Session, email: str, display_name: Optional[str]
) -> tuple[User, str]:
    """Password-less get-or-create login via the ``dev`` provider (subject = email).

    Doubly-gated at the endpoint (auth + dev-login flags).
    """
    return login_with_identity(
        session, "dev", _normalize_email(email), email, display_name
    )


# --- password provider (Phase 11.1, D25) --------------------------------------
PASSWORD_PROVIDER = "password"


def register_password_user(
    session: Session, email: str, password: str, display_name: Optional[str]
) -> tuple[User, str]:
    """Create-only registration for the local email+password provider.

    Deliberately NOT ``login_with_identity``: that helper attaches new identities
    to an existing user by email match, which for an unauthenticated register
    would let anyone who can reach the box claim an existing (OAuth/dev) account
    with their own password. An email that already has a ``User`` raises
    ``ConflictError`` instead. Only the Argon2id verifier is stored; returns the
    user plus a fresh raw session token, like the other providers.
    """
    norm = _normalize_email(email)
    if session.exec(select(User).where(User.email == norm)).first() is not None:
        raise ConflictError("an account with this email already exists")
    now = now_utc()
    user = User(
        id=new_id("usr"),
        email=norm,
        display_name=(display_name or norm.split("@")[0]).strip()[:200] or norm,
        is_admin=_bootstrap_admin(session),
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:  # unique(email) race with a concurrent register
        session.rollback()
        raise ConflictError("an account with this email already exists") from exc
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="user",
        entity_id=user.id,
    )
    session.add(
        UserIdentity(
            id=new_id("uid"),
            user_id=user.id,
            provider=PASSWORD_PROVIDER,
            provider_subject=norm,
            password_hash=hash_secret(password),
            created_at=now,
        )
    )
    raw_token = create_session(session, user.id)
    session.commit()
    session.refresh(user)
    return user, raw_token


def login_with_password(
    session: Session, email: str, password: str
) -> Optional[tuple[User, str]]:
    """Verify an email+password login; ``None`` on ANY failure.

    Unknown email, no password identity, wrong password, and inactive account
    are indistinguishable to the caller (one generic 401 at the endpoint).
    Unknown identities still burn one Argon2id verify (``dummy_verify``) so they
    cost roughly the same as a known-but-wrong one.
    """
    norm = _normalize_email(email)
    identity = session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == PASSWORD_PROVIDER,
            UserIdentity.provider_subject == norm,
        )
    ).first()
    if identity is None or not identity.password_hash:
        dummy_verify()
        return None
    if not verify_secret(identity.password_hash, password):
        return None
    user = session.get(User, identity.user_id)
    if user is None or not user.is_active:
        return None
    raw_token = create_session(session, user.id)
    session.commit()
    session.refresh(user)
    return user, raw_token


def change_password(
    session: Session,
    user: User,
    current_password: str,
    new_password: str,
    keep_raw_token: Optional[str] = None,
) -> bool:
    """Rotate the caller's password; ``False`` if ``current_password`` is wrong.

    ``ConflictError`` if the account has no password identity — setting a FIRST
    password on an OAuth/dev account is deliberately out of P11.1 scope (it
    would need its own re-auth story; register stays create-only either way).
    On success every OTHER live session for the user is revoked;
    ``keep_raw_token`` (the caller's own cookie) survives.
    """
    identity = session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == PASSWORD_PROVIDER,
            UserIdentity.user_id == user.id,
        )
    ).first()
    if identity is None or not identity.password_hash:
        raise ConflictError("this account has no password login")
    if not verify_secret(identity.password_hash, current_password):
        return False
    identity.password_hash = hash_secret(new_password)
    identity.password_must_change = False  # P16.1: a self-chosen password clears it
    session.add(identity)
    keep_hash = _hash_token(keep_raw_token) if keep_raw_token else None
    now = now_utc()
    rows = session.exec(
        select(UserSession).where(UserSession.user_id == user.id)
    ).all()
    for row in rows:
        if row.revoked_at is None and row.token_hash != keep_hash:
            row.revoked_at = now
            session.add(row)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="user",
        entity_id=user.id,
    )
    session.commit()
    return True


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


def member_candidates(session: Session, workspace_id: str) -> list[User]:
    """Active accounts not already in this workspace — the invite pick-list.

    Scoped per workspace and gated on the owner role at the endpoint, so this
    is not a directory any signed-in user can enumerate: you already manage a
    workspace, and adding someone means learning their address anyway. Already
    members are excluded because adding them is a 409.
    """
    member_ids = {m.user_id for m in list_members(session, workspace_id)}
    users = session.exec(
        select(User).where(User.is_active == True).order_by(User.email)  # noqa: E712
    ).all()
    return [u for u in users if u.id not in member_ids]


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
