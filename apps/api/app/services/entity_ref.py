"""Existence check for polymorphic (entity_type, entity_id) references.

Used by comment_service and link_service so an attachment can never point at a
row outside its project (or a non-existent one). entity_type is already validated
against REF_ENTITY_TYPES by the schema, so this only resolves + scope-checks.
"""
from sqlmodel import Session

from app.services.entity_registry import ENTITY_MODELS

# Derived from the one registry (#94) so this can never again advertise a type it
# cannot resolve. Every model here has a `project_id` column; "project" is handled
# specially below and so is excluded.
_REF_MODELS = {
    entity_type: model
    for entity_type, (model, _label) in ENTITY_MODELS.items()
    if entity_type != "project"
}


def validate_entity_ref(
    session: Session, project_id: str, entity_type: str, entity_id: str
) -> None:
    """Raise LookupError if the target doesn't exist in this project."""
    if entity_type == "project":
        if entity_id != project_id:
            raise LookupError(f"project '{entity_id}' does not match '{project_id}'")
        return

    model = _REF_MODELS.get(entity_type)
    if model is None:
        # Unreachable for schema-validated input (the registry assert keeps this
        # map aligned with REF_ENTITY_TYPES). Kept explicit so an unregistered
        # type fails with a readable message rather than a bare KeyError whose
        # 404 detail is just the type name.
        raise LookupError(f"unsupported entity_type '{entity_type}'")

    obj = session.get(model, entity_id)
    if obj is None or obj.project_id != project_id:
        raise LookupError(
            f"{entity_type} '{entity_id}' not found in project '{project_id}'"
        )
