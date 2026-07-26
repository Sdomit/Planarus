from typing import Any, Optional

from pydantic import BaseModel, Field


class ApprovalSummary(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    origin: str
    actor_ref: Optional[str]
    action_type: str
    target_entity_type: Optional[str]
    target_entity_id: Optional[str]
    # #96: the queue rendered `task:tsk_1a2b3c4d5e6f78…`, so an update proposal
    # showed field diffs without saying which row they belonged to. Resolved
    # server-side (one query per entity type on the page); None for a *.create
    # proposal, whose target does not exist yet, and for a target since deleted.
    target_title: Optional[str] = None
    risk_level: str
    status: str
    policy_version: int
    created_at: str
    expires_at: str
    decided_at: Optional[str]
    decided_by: Optional[str]
    # P16.0 (D32): decided_by resolved to a display name when it is a real user
    # id; None for the local-mode literal "local" (UI falls back to the raw value).
    decided_by_display: Optional[str] = None
    applied_at: Optional[str]
    reason: Optional[str]
    failure_reason: Optional[str]

    model_config = {"from_attributes": True}


class DiffEntry(BaseModel):
    field: str
    before: Optional[Any] = None
    after: Optional[Any] = None


class ApprovalDetail(ApprovalSummary):
    patch_checksum: str
    diff: list[DiffEntry]
    is_expired: bool
    stale_reason: Optional[str]
    # Proposals that contain secrets are rejected at creation, so a stored
    # proposal never carries one; this flag stays False but the field is kept so
    # the UI can render a redaction note consistently.
    secret_warning: bool = False


class RejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class LocalSessionResponse(BaseModel):
    token: str


class ApprovalAuditEntry(BaseModel):
    id: str
    event_type: str
    actor_type: str
    # P16.0 (D32): stamped user id + resolved display name, when a signed-in
    # user performed the audited step. Local mode leaves both None.
    actor_id: Optional[str] = None
    actor_display: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}
