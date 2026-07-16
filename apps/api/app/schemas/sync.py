from pydantic import BaseModel, Field, field_validator

from app.sync.diff import ChangeKind

_KINDS = {k.value for k in ChangeKind}


class SyncChange(BaseModel):
    entity_type: str
    entity_id: str
    kind: str

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in _KINDS:
            raise ValueError(f"kind must be one of {sorted(_KINDS)}")
        return v


class SnapshotResponse(BaseModel):
    """A replica's publishable state for a project: manifest + serialized records."""

    project_id: str
    manifest: list[list[str]]  # [entity_type, id, signature]
    records: dict[str, dict]


class PushRequest(BaseModel):
    """A client's one-sided (local→remote) changes plus the records to upsert."""

    changes: list[SyncChange] = Field(default_factory=list)
    records: dict[str, dict] = Field(default_factory=dict)


class PushResponse(BaseModel):
    applied: int
    manifest: list[list[str]]  # the remote manifest after applying
