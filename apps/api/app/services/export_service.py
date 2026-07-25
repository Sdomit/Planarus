"""Project export / import — round-trippable JSON (Phase 17.6).

Serializes a project's graph: what travels, in what order, and which references
get remapped is declared once in ``project_graph.ENTITIES`` and shared with
``project_service.duplicate_project`` and the sync manifest (#87). What stays
behind, and why, is ``project_graph.EXCLUDED``.

Export keeps original ids so relationships survive the JSON. Import remaps every
id into a fresh project and NULLs cross-instance attribution FKs (assignee /
author / updated_by) — the referenced users won't exist on the target.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from app.core.utils import new_id, now_utc
from app.models.project import Project
from app.services import project_graph
from app.services.audit_service import create_audit_event
from app.services.project_service import _unique_slug

#: Version written by ``export_project``. Bumped to 2 when status options,
#: calendar events and todos joined the graph (#87): a v2 file carries entities a
#: v1 reader would silently drop, so an older build must refuse it rather than
#: import a quietly incomplete project.
EXPORT_VERSION = 2

#: Versions ``import_project`` accepts. v1 files predate those three entities and
#: simply have no such keys, so they still import correctly.
SUPPORTED_EXPORT_VERSIONS = (1, 2)


# --- #117: bounds for an imported payload -----------------------------------
# The import body was an arbitrary `dict`, and `import_project` created ORM rows
# while iterating it, so an oversized or absurdly shaped file was only found out
# partway through writing it. These are checked in full, before the first row.
#
# The shape is not hand-written as a typed schema per collection: the collections
# ARE `project_graph.ENTITIES` (#87), so deriving the check from the registry is
# both shorter and drift-proof — a new entity is bounded the day it is added.
MAX_IMPORT_BYTES = 32 * 1024 * 1024
MAX_ROWS_PER_ENTITY = 20_000
MAX_TOTAL_ROWS = 100_000
MAX_IMPORT_DEPTH = 64
MAX_FIELD_BYTES = 4 * 1024 * 1024


def validate_import_payload(data: dict) -> None:
    """Raise ``ValueError`` unless the payload is a recognised, bounded export.

    Everything ``import_project`` will read is checked here, before it writes
    anything — so a rejected import leaves no partial project behind.
    """
    import json

    if not isinstance(data, dict):
        raise ValueError("unrecognized export format")
    if data.get("planarus_export") not in SUPPORTED_EXPORT_VERSIONS:
        raise ValueError("unrecognized export format")

    try:
        size = len(json.dumps(data).encode("utf-8"))
    except (TypeError, ValueError):
        raise ValueError("import payload is not JSON-serializable")
    if size > MAX_IMPORT_BYTES:
        raise ValueError(
            f"import payload is {size} bytes, over the "
            f"{MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit"
        )

    depth_stack = [(data, 1)]
    while depth_stack:
        node, depth = depth_stack.pop()
        if depth > MAX_IMPORT_DEPTH:
            raise ValueError(f"import payload nests deeper than {MAX_IMPORT_DEPTH} levels")
        if isinstance(node, dict):
            depth_stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            depth_stack.extend((v, depth + 1) for v in node)

    total = 0
    # "export", not "import": `copy_graph` resolves the import surface to the
    # export one (an import reads exactly what an export writes), so bounding the
    # export surface bounds precisely the collections import will consume.
    for entity in project_graph.entities_for("export"):
        rows = data.get(entity.payload_key)
        if rows is None:
            continue  # absent is fine — a v1 file simply has fewer collections
        if not isinstance(rows, list):
            raise ValueError(f"{entity.payload_key} must be a list")
        if len(rows) > MAX_ROWS_PER_ENTITY:
            raise ValueError(
                f"{entity.payload_key} has {len(rows)} rows, over the "
                f"{MAX_ROWS_PER_ENTITY} limit"
            )
        total += len(rows)
        if total > MAX_TOTAL_ROWS:
            raise ValueError(f"import exceeds {MAX_TOTAL_ROWS} total rows")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{entity.payload_key} rows must be objects")
            for key, value in row.items():
                if isinstance(value, str) and len(value.encode("utf-8")) > MAX_FIELD_BYTES:
                    raise ValueError(
                        f"{entity.payload_key}.{key} exceeds the "
                        f"{MAX_FIELD_BYTES // (1024 * 1024)} MiB field limit"
                    )


def export_project(session: Session, project_id: str) -> Optional[dict]:
    """Serialize a project + its graph to a JSON-safe dict (original ids)."""
    proj = session.get(Project, project_id)
    if proj is None:
        return None
    out: dict = {"planarus_export": EXPORT_VERSION, "project": proj.model_dump()}
    # Ids of what has been exported so far, so entities reached through a parent
    # (checklist items hang off tasks) can be collected without a second query
    # plan. Same shape as the id map the copy walk uses.
    seen: dict[str, dict[str, str]] = {}
    for entity in project_graph.entities_for("export"):
        rows = project_graph.rows_of(session, entity, project_id, seen)
        seen[entity.key] = {r.id: r.id for r in rows}
        out[entity.payload_key] = [r.model_dump() for r in rows]
    return out


def import_project(session: Session, workspace_id: str, data: dict) -> Project:
    """Create a fresh project from an export dict, remapping every id. Raises
    ValueError on an unrecognized payload."""
    validate_import_payload(data)  # #117: in full, before the first row is created
    src = data.get("project") or {}
    now = now_utc()
    new_proj = Project(
        id=new_id("proj"),
        workspace_id=workspace_id,
        title=str(src.get("title") or "Imported project")[:200],
        slug=_unique_slug(session, workspace_id, str(src.get("slug") or "imported")),
        summary=src.get("summary"),
        project_type=src.get("project_type"),
        status="idea",
        priority=src.get("priority"),
        folder_path=None,
        created_at=now,
        updated_at=now,
    )
    session.add(new_proj)
    session.flush()

    idmap: dict[str, dict[str, str]] = {"project": {src.get("id"): new_proj.id}}
    project_graph.copy_graph(
        session,
        surface="import",
        new_project_id=new_proj.id,
        now=now,
        idmap=idmap,
        rows_for=lambda entity: list(data.get(entity.payload_key, [])),
    )

    create_audit_event(
        session, event_type="import", actor_type="user", entity_type="project",
        entity_id=new_proj.id, workspace_id=workspace_id, project_id=new_proj.id,
    )
    session.commit()
    session.refresh(new_proj)
    return new_proj
