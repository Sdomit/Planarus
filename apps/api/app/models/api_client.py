"""ApiClient: external API credentials for the Phase 7C1 external HTTP surface.

One row per issued external key. The key's *capability* is fixed at creation by
two independent booleans — ``can_read`` and ``can_propose`` — with a DB-level
CHECK that at least one is true. There is **no** approve/apply permission and no
free-form scope string: the external API can only ever do bounded reads and create
pending proposals. Scope is bound to an explicit, non-empty, capped list of
project ids (serialized in ``project_ids_json``), all in ``workspace_id``.

Only the Argon2id verifier (``secret_hash``) is stored; the raw key is shown once
at creation and never persisted, logged, or returned again. Response serializers
omit ``secret_hash`` by construction.
"""
from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel


class ApiClient(SQLModel, table=True):
    __tablename__ = "apiclient"
    __table_args__ = (
        # At least one capability must be granted. Bare boolean predicate so the
        # same SQL is valid on SQLite (0/1 truthiness) and Postgres (native bool);
        # must stay in sync with migration 0007.
        CheckConstraint(
            "can_read OR can_propose",
            name="ck_apiclient_at_least_one_perm",
        ),
        # key_id is the public lookup handle for an incoming Bearer credential.
        Index("ix_apiclient_key_id", "key_id", unique=True),
        Index("ix_apiclient_workspace_id", "workspace_id"),
    )

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id")

    # Public, non-secret key handle (safe to index/log) + Argon2id verifier.
    key_id: str
    secret_hash: str

    label: str

    # Fixed capability booleans (NO approve/apply; NO free-form scope string).
    can_read: bool = Field(default=False)
    can_propose: bool = Field(default=False)

    # Explicit project scope, JSON-serialized list (validated at the service layer:
    # non-empty, unique, ≤50, every id belonging to workspace_id).
    project_ids_json: str

    enabled: bool = Field(default=True)

    created_at: str
    expires_at: str
    last_used_at: Optional[str] = None
    # Revocation is one-way in this phase (no re-enable).
    revoked_at: Optional[str] = None
