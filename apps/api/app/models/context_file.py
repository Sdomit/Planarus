from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ContextFile(SQLModel, table=True):
    """Tracks one generated Markdown file in a project's `context/` pack.

    The DB row is authoritative for generation metadata (`checksum`, `pinned`,
    `generated_at`); the on-disk file is a derived, portable export. The unique
    key is `(project_id, relative_path)` — `kind` is a categorisation that may
    repeat across files (e.g. PROJECT/CONTEXT/STATUS all share `project_context`).
    See docs/plan/03-data-model.md and docs/plan/04-filesystem-and-markdown.md.
    """

    __tablename__ = "contextfile"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "relative_path", name="uq_contextfile_project_path"
        ),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    kind: str = Field(index=True)
    relative_path: str
    checksum: str
    generated_at: str
    pinned: bool = Field(default=False)
    last_manual_edit_at: Optional[str] = None
    token_estimate: Optional[int] = None
    created_at: str
    updated_at: str
