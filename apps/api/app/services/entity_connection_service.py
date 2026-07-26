"""Validated CRUD for bounded planning-entity connections (Phase 25)."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.constants import CONNECTION_ENTITY_TYPES, CONNECTION_RELATION_TYPES
from app.core.utils import new_id, now_utc
from app.models.entity_connection import EntityConnection
from app.models.project import Project
from app.schemas.entity_connection import EntityConnectionCreate
from app.services.audit_service import create_audit_event
from app.services.entity_ref import validate_entity_ref

# Every supported direction is explicit. ``related_to`` is undirected in the
# product, but is stored in a deterministic lexical order for deduplication.
_RELATION_ENDPOINTS: dict[str, set[tuple[str, str]]] = {
    "depends_on": {("task", "task")},
    "implements": {("task", "decision")},
    "mitigates": {("task", "risk")},
    "contributes_to": {("task", "milestone")},
    "references": {
        ("phase", "doc"),
        ("task", "doc"),
        ("decision", "doc"),
        ("risk", "doc"),
        ("milestone", "doc"),
    },
}


def normalize_connection_patch(patch: dict) -> dict:
    """Return a copy with undirected connections in one canonical orientation."""
    normalized = dict(patch)
    if normalized.get("relation_type") == "related_to":
        source = (normalized.get("source_entity_type"), normalized.get("source_entity_id"))
        target = (normalized.get("target_entity_type"), normalized.get("target_entity_id"))
        if target < source:
            normalized.update(
                source_entity_type=target[0],
                source_entity_id=target[1],
                target_entity_type=source[0],
                target_entity_id=source[1],
            )
    return normalized


def _assert_relation_compatible(
    relation_type: str,
    source_entity_type: str,
    target_entity_type: str,
) -> None:
    if relation_type == "related_to":
        return
    if (source_entity_type, target_entity_type) not in _RELATION_ENDPOINTS.get(
        relation_type, set()
    ):
        raise ValueError(
            f"{relation_type} does not support {source_entity_type} -> {target_entity_type}"
        )


def lock_dependency_graph(session: Session, project_id: str) -> None:
    """Serialize every writer that can add a ``depends_on`` edge to one project.

    Acyclicity is a property of the whole graph, so neither a row constraint nor
    the canonical unique index can hold it: two transactions each adding one edge
    both walk an acyclic graph, both pass, and together they commit a cycle. The
    unique index only rejects the *same* edge twice, which is a different bug.

    The project row is the graph's only single owner, so writers queue on it. It
    is claimed with a self-assigning UPDATE rather than ``SELECT ... FOR UPDATE``
    because the two engines need locking at different moments and this one
    statement covers both:

    - PostgreSQL (READ COMMITTED) takes a row-level exclusive lock held to
      commit. The second writer blocks at this statement, and once the first
      commits it walks a graph that contains the new edge.
    - SQLite has no row locks and ignores ``FOR UPDATE`` entirely, so a plain
      SELECT would leave it unprotected: its write lock is taken at the first
      *write*, which without this would come after the walk. Issuing a write here
      moves that lock ahead of the walk, and ``busy_timeout`` (see
      ``db/session.py``) makes the second writer wait for it rather than fail.

    ``updated_at`` is assigned to itself: the row must be written to be locked,
    but a connection is not an edit of the project and must not look like one.
    """
    session.execute(
        sa_update(Project)
        .where(Project.id == project_id)
        .values(updated_at=Project.updated_at)
    )


def _would_create_dependency_cycle(
    session: Session, project_id: str, source_task_id: str, target_task_id: str
) -> bool:
    """Adding source -> target cycles when target already reaches source."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    rows = session.exec(
        select(EntityConnection).where(
            EntityConnection.project_id == project_id,
            EntityConnection.relation_type == "depends_on",
        )
    ).all()
    for row in rows:
        adjacency[row.source_entity_id].add(row.target_entity_id)

    pending = deque([target_task_id])
    seen: set[str] = set()
    while pending:
        current = pending.popleft()
        if current == source_task_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(adjacency[current] - seen)
    return False


def validate_connection_shape(values: dict) -> dict:
    """The endpoint checks that need no database; returns the canonical copy.

    Split out of ``validate_connection_values`` so an import payload can be
    checked before a row exists (``project_graph`` declares it as this entity's
    ``row_check``). Both callers share one definition of a legal connection —
    two of them would drift, which is exactly what #87 was about.
    """
    required = {
        "relation_type",
        "source_entity_type",
        "source_entity_id",
        "target_entity_type",
        "target_entity_id",
    }
    if not required <= set(values):
        raise ValueError("connection must include exactly the canonical endpoint fields")
    data = normalize_connection_patch({key: values[key] for key in required})
    if not all(isinstance(value, str) and value for value in data.values()):
        raise ValueError("connection fields must be non-blank strings")
    relation_type = data["relation_type"]
    source_type = data["source_entity_type"]
    target_type = data["target_entity_type"]
    if relation_type not in CONNECTION_RELATION_TYPES:
        raise ValueError("unknown connection relation type")
    if source_type not in CONNECTION_ENTITY_TYPES or target_type not in CONNECTION_ENTITY_TYPES:
        raise ValueError("unknown connection entity type")
    _assert_relation_compatible(relation_type, source_type, target_type)
    if source_type == target_type and data["source_entity_id"] == data["target_entity_id"]:
        raise ValueError("an entity cannot be connected to itself")
    return data


def validate_connection_values(
    session: Session,
    project_id: str,
    values: dict,
    *,
    check_duplicate: bool = True,
) -> dict:
    """Validate a raw normalized-compatible connection; return its canonical copy.

    Raises ``LookupError`` for a project/endpoint outside scope and ``ValueError``
    for incompatible, self, duplicate, or cyclic connections. It never mutates.
    """
    if session.get(Project, project_id) is None:
        raise LookupError(f"project '{project_id}' not found")
    required = {
        "relation_type",
        "source_entity_type",
        "source_entity_id",
        "target_entity_type",
        "target_entity_id",
    }
    if set(values) != required:
        raise ValueError("connection must include exactly the canonical endpoint fields")
    data = validate_connection_shape(values)
    relation_type = data["relation_type"]
    source_type = data["source_entity_type"]
    source_id = data["source_entity_id"]
    target_type = data["target_entity_type"]
    target_id = data["target_entity_id"]
    validate_entity_ref(session, project_id, source_type, source_id)
    validate_entity_ref(session, project_id, target_type, target_id)
    if relation_type == "depends_on" and _would_create_dependency_cycle(
        session, project_id, source_id, target_id
    ):
        raise ValueError("dependency connection would create a cycle")
    if check_duplicate:
        existing = session.exec(
            select(EntityConnection.id).where(
                EntityConnection.project_id == project_id,
                EntityConnection.relation_type == relation_type,
                EntityConnection.source_entity_type == source_type,
                EntityConnection.source_entity_id == source_id,
                EntityConnection.target_entity_type == target_type,
                EntityConnection.target_entity_id == target_id,
            )
        ).first()
        if existing is not None:
            raise ValueError("that connection already exists")
    return data


def list_connections(
    session: Session,
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> list[EntityConnection]:
    if (entity_type is None) != (entity_id is None):
        raise ValueError("entity_type and entity_id must be supplied together")
    if session.get(Project, project_id) is None:
        raise LookupError(f"project '{project_id}' not found")
    stmt = select(EntityConnection).where(EntityConnection.project_id == project_id)
    if entity_type is not None and entity_id is not None:
        stmt = stmt.where(
            or_(
                (EntityConnection.source_entity_type == entity_type)
                & (EntityConnection.source_entity_id == entity_id),
                (EntityConnection.target_entity_type == entity_type)
                & (EntityConnection.target_entity_id == entity_id),
            )
        )
    return list(session.exec(stmt.order_by(EntityConnection.created_at, EntityConnection.id)).all())


def create_connection(
    session: Session,
    project_id: str,
    data: EntityConnectionCreate | dict,
    *,
    commit: bool = True,
    audit: bool = True,
) -> EntityConnection:
    values = data.model_dump() if isinstance(data, EntityConnectionCreate) else dict(data)
    if values.get("relation_type") == "depends_on":
        # Before the walk, not after: the cycle check is only sound if no other
        # writer can add an edge between reading the graph and inserting into it.
        # Only dependency edges need it — nothing else has a whole-graph rule, so
        # nothing else should queue behind one.
        lock_dependency_graph(session, project_id)
    values = validate_connection_values(session, project_id, values)
    now = now_utc()
    connection = EntityConnection(
        id=new_id("con"),
        project_id=project_id,
        **values,
        created_at=now,
        updated_at=now,
    )
    session.add(connection)
    try:
        session.flush()
    except IntegrityError as exc:
        # A concurrent creation can pass the read check above. The table's unique
        # constraint is the final authority; present its conflict without leaking
        # database detail.
        session.rollback()
        raise ValueError("that connection already exists") from exc
    if audit:
        create_audit_event(
            session,
            event_type="create",
            actor_type="human",
            entity_type="entity_connection",
            entity_id=connection.id,
            project_id=project_id,
        )
    if commit:
        session.commit()
        session.refresh(connection)
    return connection


def delete_connection(session: Session, connection_id: str) -> bool:
    connection = session.get(EntityConnection, connection_id)
    if connection is None:
        return False
    session.delete(connection)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="entity_connection",
        entity_id=connection_id,
        project_id=connection.project_id,
    )
    session.commit()
    return True


def delete_for_entity(
    session: Session, project_id: str, entity_type: str, entity_id: str
) -> None:
    """Remove connections owned by an entity inside its parent delete transaction."""
    session.execute(
        sa_delete(EntityConnection).where(
            EntityConnection.project_id == project_id,
            or_(
                (EntityConnection.source_entity_type == entity_type)
                & (EntityConnection.source_entity_id == entity_id),
                (EntityConnection.target_entity_type == entity_type)
                & (EntityConnection.target_entity_id == entity_id),
            ),
        )
    )
