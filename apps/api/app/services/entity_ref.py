"""Existence check for polymorphic (entity_type, entity_id) references.

Used by comment_service and link_service so an attachment can never point at a
row outside its project (or a non-existent one). entity_type is already validated
against REF_ENTITY_TYPES by the schema, so this only resolves + scope-checks.
"""
from sqlmodel import Session

from app.models.blocker import Blocker
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.task import Task

# Every model here has a `project_id` column; "project" is handled specially.
_REF_MODELS = {
    "phase": Phase,
    "stage": Stage,
    "task": Task,
    "decision": Decision,
    "risk": Risk,
    "blocker": Blocker,
    "milestone": Milestone,
    "doc": Doc,
}


def validate_entity_ref(
    session: Session, project_id: str, entity_type: str, entity_id: str
) -> None:
    """Raise LookupError if the target doesn't exist in this project."""
    if entity_type == "project":
        if entity_id != project_id:
            raise LookupError(f"project '{entity_id}' does not match '{project_id}'")
        return

    model = _REF_MODELS[entity_type]
    obj = session.get(model, entity_id)
    if obj is None or obj.project_id != project_id:
        raise LookupError(
            f"{entity_type} '{entity_id}' not found in project '{project_id}'"
        )
