"""Pydantic contracts for the Phase 6A Context Pack Builder.

Preview is generation-only: these schemas describe a request that selects
canonical sources and a response that returns deterministic Markdown plus a
manifest, warnings, truncation details, and masked secret findings. Nothing here
persists pack bodies, selections, or findings.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.prompt import profiles, tokens


class ContextPackSelection(BaseModel):
    """User-controlled source selection. All fields are optional with safe
    defaults — an empty selection yields a baseline pack from canonical state."""

    document_ids: list[str] = Field(default_factory=list)
    document_order: list[str] = Field(default_factory=list)
    pinned_source_ids: list[str] = Field(default_factory=list)
    excluded_source_ids: list[str] = Field(default_factory=list)
    include_done_tasks: bool = False
    include_closed_risks: bool = False
    include_resolved_blockers: bool = False
    include_all_decisions: bool = False
    include_audit_slice: bool = False


class ContextPackPreviewRequest(BaseModel):
    profile: str
    target_tool: str
    budget_preset: str = tokens.DEFAULT_BUDGET_PRESET
    objective: str = ""
    selection: ContextPackSelection = Field(default_factory=ContextPackSelection)
    # Default false so the refusal is opt-out, not opt-in: a caller that has not
    # been told a governance file is missing must not receive a pack whose scope
    # section is empty under an "authoritative" heading (#98).
    allow_incomplete_governance: bool = False

    @field_validator("profile")
    @classmethod
    def _validate_profile(cls, v: str) -> str:
        if not profiles.is_valid_profile(v):
            allowed = ", ".join(p.key for p in profiles.all_profiles())
            raise ValueError(f"profile must be one of: {allowed}")
        return v

    @field_validator("target_tool")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        if not profiles.is_valid_target(v):
            allowed = ", ".join(profiles.TARGET_TOOLS)
            raise ValueError(f"target_tool must be one of: {allowed}")
        return v

    @field_validator("budget_preset")
    @classmethod
    def _validate_budget(cls, v: str) -> str:
        if not tokens.is_valid_budget(v):
            allowed = ", ".join(tokens.BUDGET_PRESETS.keys())
            raise ValueError(f"budget_preset must be one of: {allowed}")
        return v

    @field_validator("objective")
    @classmethod
    def _validate_objective(cls, v: str) -> str:
        # The objective is authoritative human input; cap its length so it cannot
        # itself blow the budget. Content is otherwise unconstrained.
        if len(v) > 8_000:
            raise ValueError("objective exceeds the 8000-character limit")
        return v


# --- response models -------------------------------------------------------


class SecretFindingRead(BaseModel):
    pattern_label: str
    masked_preview: str
    source_ref: str
    count: int


class ManifestEntry(BaseModel):
    source_id: str
    label: str
    kind: str  # canonical | derived | authored
    included: bool
    truncated: bool
    pinned: bool
    flagged: bool
    token_estimate: int
    version: str
    note: Optional[str] = None


class TruncationEntry(BaseModel):
    source_id: str
    reason: str  # e.g. "budget-truncate" | "budget-drop"


class ProfileMeta(BaseModel):
    key: str
    version: int
    label: str
    include_git_checklist: bool


class ContextPackPreviewResponse(BaseModel):
    markdown: str
    pack_checksum: str
    token_estimate: int  # APPROXIMATE — heuristic, not a real tokenizer
    budget_preset: str
    budget_limit: int
    over_budget: bool
    profile: ProfileMeta
    target_tool: str
    manifest: list[ManifestEntry]
    warnings: list[str]
    truncations: list[TruncationEntry]
    secret_findings: list[SecretFindingRead]


# --- sources + profiles list models ---------------------------------------


class StructuredSourceItem(BaseModel):
    source_id: str
    label: str
    kind: str
    default_included: bool
    optional: bool
    token_estimate: int


class DocumentSourceItem(BaseModel):
    source_id: str
    doc_id: str
    title: str
    doc_type: str
    status: str
    token_estimate: int


class GovernanceSourceItem(BaseModel):
    source_id: str
    relative_path: str
    available: bool
    status: str  # ok | drifted | missing-on-disk | no-record | unavailable
    token_estimate: int


class ContextPackSourcesResponse(BaseModel):
    project_id: str
    has_folder: bool
    structured: list[StructuredSourceItem]
    documents: list[DocumentSourceItem]
    governance: list[GovernanceSourceItem]
    warnings: list[str]


class ProfileListItem(BaseModel):
    key: str
    version: int
    label: str
    description: str
    default_target: str
    include_git_checklist: bool


class ProfilesResponse(BaseModel):
    target_tools: list[str]
    budget_presets: dict[str, int]
    default_budget_preset: str
    profiles: list[ProfileListItem]
