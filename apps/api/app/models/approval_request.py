from typing import Optional

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel

from app.core.constants import (
    approval_action_type_check_sql,
    approval_origin_check_sql,
    approval_risk_level_check_sql,
    approval_status_check_sql,
    approval_target_entity_type_check_sql,
)


class ApprovalRequest(SQLModel, table=True):
    """A single proposed mutation awaiting local human review (Phase 7A).

    One proposal == one action. Every field in the *binding* block is immutable
    after creation; only the lifecycle bookkeeping block (status, decided_*,
    applied_*, reason, failure_reason) is written by ``approval_service``.
    """

    __tablename__ = "approvalrequest"
    __table_args__ = (
        CheckConstraint(approval_status_check_sql(), name="ck_approval_status"),
        CheckConstraint(approval_origin_check_sql(), name="ck_approval_origin"),
        CheckConstraint(
            approval_risk_level_check_sql(), name="ck_approval_risk_level"
        ),
        CheckConstraint(
            approval_action_type_check_sql(), name="ck_approval_action_type"
        ),
        CheckConstraint(
            approval_target_entity_type_check_sql(),
            name="ck_approval_target_entity_type",
        ),
        Index("ix_approval_workspace_status", "workspace_id", "status"),
        Index("ix_approval_project_status", "project_id", "status"),
        Index("ix_approval_status", "status"),
        Index("ix_approval_expires_at", "expires_at"),
        Index("ix_approval_origin", "origin"),
        # Phase 7B: idempotency is unique only among *active* proposals, so an
        # identical request is allowed again once the earlier one is truly terminal
        # (rejected/expired/invalidated/applied). "failed" is treated as active
        # because apply() can retry it — an identical re-proposal must dedupe to it
        # rather than create a second row that could double-apply. Keyed by
        # (origin, actor_ref, idempotency_key). Local proposals leave
        # idempotency_key NULL (NULLs are distinct), so they never collide. This
        # MUST match migration 0006 — tests build the schema from this model.
        Index(
            "uq_approval_active_idem",
            "origin",
            "actor_ref",
            "idempotency_key",
            unique=True,
            sqlite_where=text("status IN ('pending', 'approved', 'applying', 'failed')"),
        ),
    )

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    project_id: str = Field(foreign_key="project.id", index=True)

    # --- immutable binding (set once at creation) ---
    origin: str = Field(default="local")
    actor_ref: Optional[str] = None
    action_type: str
    target_entity_type: Optional[str] = None
    target_entity_id: Optional[str] = None
    proposed_patch_json: str
    patch_checksum: str
    base_target_fingerprint: Optional[str] = None
    base_versions_json: Optional[str] = None
    policy_version: int
    risk_level: str = Field(default="low")
    idempotency_key: Optional[str] = None

    # --- lifecycle bookkeeping (engine-written only) ---
    status: str = Field(default="pending")
    reason: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: str
    expires_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    applied_at: Optional[str] = None
    applied_audit_event_id: Optional[str] = Field(
        default=None, foreign_key="auditevent.id", index=True
    )
