from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import risk_severity_check_sql


class Risk(SQLModel, table=True):
    __tablename__ = "risk"
    # Phase 15.5: no `status` CHECK — a risk may take a custom status (validated
    # in the service layer). `severity` keeps its canonical CHECK.
    __table_args__ = (
        CheckConstraint(risk_severity_check_sql(), name="ck_risk_severity"),
        Index("ix_risk_project_status", "project_id", "status"),
        Index("ix_risk_project_severity", "project_id", "severity"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    # Phase 19 (D45): optional phase this risk threatens. NULL = a project-wide
    # risk that isn't scoped to one phase.
    phase_id: Optional[str] = Field(default=None, foreign_key="phase.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    severity: str
    status: str = Field(default="open")
    mitigation: Optional[str] = None
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
