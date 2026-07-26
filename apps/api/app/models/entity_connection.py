from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import (
    entity_connection_entity_type_check_sql,
    entity_connection_relation_type_check_sql,
)


class EntityConnection(SQLModel, table=True):
    """A typed, same-project relationship between two planning entities.

    The endpoint ids are intentionally polymorphic, so project ownership and
    relation compatibility are enforced in ``entity_connection_service``. The
    database still owns the bounded enum and duplicate invariants.
    """

    __tablename__ = "entity_connection"
    __table_args__ = (
        CheckConstraint(
            entity_connection_relation_type_check_sql(),
            name="ck_entity_connection_relation_type",
        ),
        CheckConstraint(
            entity_connection_entity_type_check_sql("source_entity_type"),
            name="ck_entity_connection_source_entity_type",
        ),
        CheckConstraint(
            entity_connection_entity_type_check_sql("target_entity_type"),
            name="ck_entity_connection_target_entity_type",
        ),
        UniqueConstraint(
            "project_id",
            "relation_type",
            "source_entity_type",
            "source_entity_id",
            "target_entity_type",
            "target_entity_id",
            name="uq_entity_connection_canonical",
        ),
        Index(
            "ix_entity_connection_project_source",
            "project_id",
            "source_entity_type",
            "source_entity_id",
        ),
        Index(
            "ix_entity_connection_project_target",
            "project_id",
            "target_entity_type",
            "target_entity_id",
        ),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    relation_type: str
    source_entity_type: str
    source_entity_id: str
    target_entity_type: str
    target_entity_id: str
    created_at: str
    updated_at: str
