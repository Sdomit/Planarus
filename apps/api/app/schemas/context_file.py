from typing import Optional

from pydantic import BaseModel


class ContextFileRead(BaseModel):
    id: str
    project_id: str
    kind: str
    relative_path: str
    checksum: str
    generated_at: str
    pinned: bool
    last_manual_edit_at: Optional[str]
    token_estimate: Optional[int]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ContextFileUpdate(BaseModel):
    """Only the pin state is human-editable; content is regenerated, not edited."""

    pinned: bool


class ContextFileContent(BaseModel):
    relative_path: str
    content: Optional[str]
    drifted: bool


class ContextFileDiff(BaseModel):
    relative_path: str
    diff: str


class FileOutcomeRead(BaseModel):
    relative_path: str
    kind: str
    status: str
    pinned: bool
    drifted: bool


class RegenReportRead(BaseModel):
    project_id: str
    generated_at: str
    written: int
    drifted: int
    outcomes: list[FileOutcomeRead]
