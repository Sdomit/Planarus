"""Existence check for polymorphic (entity_type, entity_id) references.

Used by comment_service and link_service so an attachment can never point at a
row outside its project (or a non-existent one). entity_type is already validated
against REF_ENTITY_TYPES by the schema, so this only resolves + scope-checks.
"""
from typing import Iterable

from sqlmodel import Session, select

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


def filter_existing_refs(
    session: Session, project_id: str, refs: Iterable[tuple[str, str]]
) -> set[tuple[str, str]]:
    """Batch form of ``validate_entity_ref``: which of ``refs`` exist in this project.

    One query per distinct entity *type* rather than one per reference.
    ``validate_entity_ref`` is a ``session.get`` per call, and SQLAlchemy does not
    cache negative lookups — so a caller checking N references paid N round-trips
    even when every one of them was fabricated. `mention_service` derives its rows
    from a 2 MB document that can name tens of thousands of references, which made
    that per-reference cost a save-time amplification vector rather than a
    micro-optimisation.

    Silently drops what does not resolve (unknown type, wrong project, missing
    row), which is what the derived-projection callers want: a reference to
    something that is not there is simply not a reference. Callers needing the
    *reason* should still use ``validate_entity_ref``.
    """
    by_type: dict[str, set[str]] = {}
    for entity_type, entity_id in refs:
        by_type.setdefault(entity_type, set()).add(entity_id)

    valid: set[tuple[str, str]] = set()
    for entity_type, ids in by_type.items():
        if entity_type == "project":
            # Not a table lookup: "the project" is in scope iff it is this one.
            if project_id in ids:
                valid.add(("project", project_id))
            continue
        model = _REF_MODELS.get(entity_type)
        if model is None:
            continue
        rows = session.exec(
            select(model.id).where(  # type: ignore[attr-defined]
                model.id.in_(ids),  # type: ignore[attr-defined]
                model.project_id == project_id,  # type: ignore[attr-defined]
            )
        ).all()
        valid.update((entity_type, row_id) for row_id in rows)
    return valid
