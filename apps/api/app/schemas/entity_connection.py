from pydantic import BaseModel, Field, field_validator

from app.core.constants import CONNECTION_ENTITY_TYPES, CONNECTION_RELATION_TYPES

_ENTITY_TYPES = frozenset(CONNECTION_ENTITY_TYPES)
_RELATION_TYPES = frozenset(CONNECTION_RELATION_TYPES)


class EntityConnectionCreate(BaseModel):
    relation_type: str
    source_entity_type: str
    source_entity_id: str = Field(min_length=1)
    target_entity_type: str
    target_entity_id: str = Field(min_length=1)

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, value: str) -> str:
        if value not in _RELATION_TYPES:
            raise ValueError(
                f"relation_type must be one of: {', '.join(sorted(_RELATION_TYPES))}"
            )
        return value

    @field_validator("source_entity_type", "target_entity_type")
    @classmethod
    def validate_entity_type(cls, value: str) -> str:
        if value not in _ENTITY_TYPES:
            raise ValueError(
                f"entity type must be one of: {', '.join(sorted(_ENTITY_TYPES))}"
            )
        return value


class EntityConnectionRead(EntityConnectionCreate):
    id: str
    project_id: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
