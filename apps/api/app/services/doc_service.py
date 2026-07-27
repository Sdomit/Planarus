"""Service layer for project documents (Phase 5).

Source-of-truth hierarchy:
  content_json (canonical) → markdown_cache (derived, sent by frontend) → disk export (snapshot)

No external AI write surface, MCP, or approval queue in Phase 5.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from app.core import actor
from app.core.exceptions import ConflictError, NotFoundError
from app.core.hierarchy import MAX_DEPTH, validate_parent
from app.core.utils import new_id, now_utc
from app.fsmemory import atomic_io
from app.fsmemory.locks import project_lock
from app.fsmemory.project_root import resolve_project_root_or_none
from app.models.comment import Comment
from app.models.doc import Doc
from app.models.link import Link
from app.models.mention import Mention
from app.models.project import Project
from app.schemas.doc import DocCreate, DocExportResponse, DocUpdate
from app.services import entity_connection_service, mention_service
from app.services.audit_service import create_audit_event

# Maps doc_type → export subfolder within docs/
_TYPE_SUBFOLDER: dict[str, str] = {
    "spec": "docs/product",
    "research": "docs/research",
    "plan": "docs/implementation",
    "note": "docs",
    "reference": "docs",
    "other": "docs",
}

_EMPTY_CONTENT_JSON = '{"type": "doc", "content": [{"type": "paragraph"}]}'
# Phase 13: an empty Excalidraw scene. The frontend hydrates initialData from it.
_EMPTY_CANVAS_JSON = (
    '{"type": "excalidraw", "version": 2, "source": "planarus",'
    ' "elements": [], "appState": {}, "files": {}}'
)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def _slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "doc"


def _escape_like(term: str) -> str:
    """Neutralise LIKE wildcards so searching for "50%" or "a_b" matches literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _unique_slug(session: Session, project_id: str, base: str) -> str:
    candidate = base
    n = 1
    while True:
        existing = session.exec(
            select(Doc).where(Doc.project_id == project_id, Doc.slug == candidate)
        ).first()
        if existing is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_doc(session: Session, project_id: str, payload: DocCreate) -> Doc:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id!r} not found")

    parent_doc_id = validate_parent(
        session,
        Doc,
        parent_id=payload.parent_doc_id,
        project_id=project_id,
        parent_attr="parent_doc_id",
        label="parent doc",
    )

    base_slug = _slugify(payload.slug or payload.title)
    slug = _unique_slug(session, project_id, base_slug)

    ts = now_utc()
    doc = Doc(
        id=new_id("doc"),
        project_id=project_id,
        parent_doc_id=parent_doc_id,
        title=payload.title,
        slug=slug,
        doc_type=payload.doc_type,
        editor_format=payload.editor_format,
        content_json=(
            _EMPTY_CANVAS_JSON
            if payload.editor_format == "excalidraw"
            else _EMPTY_CONTENT_JSON
        ),
        markdown_cache="",
        status=payload.status,
        color=payload.color,
        sort_order=payload.sort_order,
        version=1,
        updated_by=actor.current_actor_id(),  # P16.3: creator = first editor
        created_at=ts,
        updated_at=ts,
    )
    session.add(doc)
    session.flush()
    # Always empty at creation (content_json starts as one of the two constants
    # above) — wired for symmetry with update_doc, per plan 23.
    mention_service.sync_mentions(session, project_id, doc.id, doc.content_json)
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="doc",
        entity_id=doc.id,
        project_id=project_id,
        payload_json=json.dumps({"title": doc.title, "doc_type": doc.doc_type}),
    )
    session.commit()
    session.refresh(doc)
    return doc


def get_doc(session: Session, doc_id: str) -> Optional[Doc]:
    return session.get(Doc, doc_id)


def list_docs(
    session: Session,
    project_id: str,
    *,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    parent_doc_id: Optional[str] = None,
    include_archived: bool = False,
    q: Optional[str] = None,
) -> list[Doc]:
    stmt = select(Doc).where(Doc.project_id == project_id)
    if not include_archived:
        stmt = stmt.where(Doc.archived_at.is_(None))  # type: ignore[union-attr]
    if q is not None and q.strip():
        # Case-insensitive substring over title AND body. Searching markdown_cache
        # rather than the excerpt means a hit deep in a long note still counts.
        # ponytail: LIKE, not FTS — a local project's notes are hundreds of rows,
        # not millions. Add an FTS5 table if a scan ever shows up in a profile.
        needle = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                func.lower(Doc.title).like(func.lower(needle), escape="\\"),
                func.lower(Doc.markdown_cache).like(func.lower(needle), escape="\\"),
            )
        )
    if doc_type is not None:
        stmt = stmt.where(Doc.doc_type == doc_type)
    if status is not None:
        stmt = stmt.where(Doc.status == status)
    if parent_doc_id is not None:
        stmt = stmt.where(Doc.parent_doc_id == parent_doc_id)
    stmt = stmt.order_by(Doc.sort_order, Doc.created_at)
    return list(session.exec(stmt).all())


def update_doc(session: Session, doc_id: str, payload: DocUpdate) -> Doc:
    doc = session.get(Doc, doc_id)
    if doc is None:
        raise NotFoundError(f"Doc {doc_id!r} not found")

    if payload.version != doc.version:
        # #99: was LookupError, which the app-wide convention maps to 404 — for a
        # document that demonstrably exists. `endpoints/docs.py` compensated by
        # re-mapping LookupError to 409 locally, inverting the convention twice to
        # land on the right answer. ConflictError says it once, here.
        raise ConflictError(
            f"Version conflict: expected {payload.version}, got {doc.version}"
        )

    # content_json and markdown_cache must always arrive together.
    if (payload.content_json is None) != (payload.markdown_cache is None):
        raise TypeError("content_json and markdown_cache must be provided together")

    # NOT-NULL columns: a null here is still "unchanged". The column cannot hold
    # NULL, so there is no state for an explicit null to express.
    values: dict = {}
    if payload.title is not None:
        values["title"] = payload.title
    if payload.doc_type is not None:
        values["doc_type"] = payload.doc_type
    if payload.status is not None:
        values["status"] = payload.status
    if payload.sort_order is not None:
        values["sort_order"] = payload.sort_order
    if payload.content_json is not None:
        values["content_json"] = payload.content_json
        values["markdown_cache"] = payload.markdown_cache

    # NULLABLE columns: *presence* decides, not the value (#156). Keying these off
    # `is not None` made null indistinguishable from omitted, so an archived doc
    # could never be un-archived and a child doc could never move back to root —
    # the NULL state was simply unreachable through the only write path there is.
    provided = payload.model_fields_set
    if "parent_doc_id" in provided:
        values["parent_doc_id"] = (
            validate_parent(
                session,
                Doc,
                parent_id=payload.parent_doc_id,
                project_id=doc.project_id,
                child_id=doc.id,
                parent_attr="parent_doc_id",
                label="parent doc",
            )
            if payload.parent_doc_id is not None
            else None
        )
    if "archived_at" in provided:
        values["archived_at"] = payload.archived_at
    if "color" in provided:
        # An explicit null now clears the swatch. "default" stays accepted as the
        # older clear-sentinel so existing clients keep working.
        values["color"] = None if payload.color == "default" else payload.color

    if values:
        values["version"] = payload.version + 1
        values["updated_at"] = now_utc()
        values["updated_by"] = actor.current_actor_id()  # P16.3: who last saved it
        # Atomic compare-and-swap on version (#156). The check above is a fast,
        # friendly pre-check; it is NOT the guard, because between that read and
        # this write another writer can commit. Under SQLite's single writer that
        # gap is unreachable, but on the LAN/Postgres path two saves from the same
        # version both passed it and the second silently overwrote the first.
        # rowcount 0 means someone else won the race.
        cas = session.execute(
            sa_update(Doc)
            .where(Doc.id == doc_id, Doc.version == payload.version)
            .values(**values)
        )
        if cas.rowcount != 1:
            # Discards the whole transaction, not just the failed UPDATE. Safe
            # because this route does one write and nothing else; the pre-check
            # above raises the same ConflictError WITHOUT rolling back, so anyone
            # wrapping two writes in one transaction here must reconcile the two
            # paths first.
            session.rollback()
            raise ConflictError(
                f"Version conflict: expected {payload.version}, but the document "
                "was changed by another writer"
            )
        session.refresh(doc)
        # Mentions are a projection of content_json (plan 23) — re-derive only
        # when that column actually moved; a title/status/etc-only save leaves
        # the existing backlinks untouched, and re-parsing them would be wasted
        # work at best (they can't have changed).
        if payload.content_json is not None:
            mention_service.sync_mentions(session, doc.project_id, doc.id, doc.content_json)

    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="doc",
        entity_id=doc.id,
        project_id=doc.project_id,
        payload_json=json.dumps({"version": doc.version}),
    )
    session.commit()
    session.refresh(doc)
    return doc


def repair_parent_integrity(session: Session, *, dry_run: bool = False) -> list[dict]:
    """Find and clear parent links that ``validate_parent`` would now reject.

    Data written before #116 can hold a cross-project parent, a self-parent, a
    parent that no longer exists, or a cycle. Each is reported as
    ``{doc_id, project_id, parent_doc_id, reason}``; with ``dry_run`` the rows
    are reported and left alone, so an operator can look before anything moves.

    Data-only, so it is a service call rather than an Alembic revision: it is
    safe to re-run, it reports before it writes, and it needs no schema change.
    """
    docs = session.exec(select(Doc).where(Doc.parent_doc_id.is_not(None))).all()  # type: ignore[union-attr]
    by_id = {d.id: d for d in docs}
    findings: list[dict] = []

    for doc in docs:
        parent = by_id.get(doc.parent_doc_id) or session.get(Doc, doc.parent_doc_id)
        if doc.parent_doc_id == doc.id:
            reason = "self-parent"
        elif parent is None:
            reason = "parent missing"
        elif parent.project_id != doc.project_id:
            reason = "parent in another project"
        else:
            reason = ""
            seen, node = {doc.id}, parent
            for _ in range(MAX_DEPTH):
                if node is None or node.id in seen:
                    reason = "cycle" if node is not None else ""
                    break
                seen.add(node.id)
                if node.parent_doc_id is None:
                    break
                node = by_id.get(node.parent_doc_id) or session.get(Doc, node.parent_doc_id)
            else:
                reason = "chain too deep"
        if not reason:
            continue

        findings.append(
            {
                "doc_id": doc.id,
                "project_id": doc.project_id,
                "parent_doc_id": doc.parent_doc_id,
                "reason": reason,
            }
        )
        if not dry_run:
            doc.parent_doc_id = None
            session.add(doc)

    if findings and not dry_run:
        session.commit()
    return findings


def delete_doc(session: Session, doc_id: str) -> bool:
    """Hard-delete a doc, its comments/links (attached via entity_type='doc'),
    its own outbound mentions (source_doc_id — a real FK, so it must go before
    the doc does), and promote any child docs to top-level (parent_doc_id
    cleared, so the FK doesn't block the delete). Mirrors delete_task's
    owned-children cleanup.

    Mentions *targeting* this doc (target_type='doc', target_id=doc_id) are left
    alone, same as a Link/Comment pointing at a deleted entity: target_id is a
    polymorphic string, not an FK, so nothing blocks the delete, and plan 23
    already treats a dangling backlink as expected — annotated "(deleted)" on
    read rather than cleaned up eagerly.
    """
    doc = session.get(Doc, doc_id)
    if doc is None:
        return False
    project_id = doc.project_id
    now = now_utc()

    for comment in session.exec(
        select(Comment).where(Comment.entity_type == "doc", Comment.entity_id == doc_id)
    ).all():
        session.delete(comment)
    for link in session.exec(
        select(Link).where(Link.entity_type == "doc", Link.entity_id == doc_id)
    ).all():
        session.delete(link)
    for mention in session.exec(
        select(Mention).where(Mention.source_doc_id == doc_id)
    ).all():
        session.delete(mention)
    # Project-scoped as defence in depth (#116). The normal path only ever
    # touches this project's documents.
    for child in session.exec(
        select(Doc).where(Doc.parent_doc_id == doc_id, Doc.project_id == project_id)
    ).all():
        child.parent_doc_id = None
        child.updated_at = now
        session.add(child)

    entity_connection_service.delete_for_entity(session, project_id, "doc", doc_id)

    # A cross-project child can no longer be created, but one written before
    # #116 still points here, and the self-FK will not let this row be deleted
    # while it does. Clearing it is unavoidable, so do it as a visible repair
    # rather than silently inside the scoped loop above: no `updated_at` bump,
    # so the other project's document is not made to look edited by a delete it
    # had no part in. `repair_parent_integrity` clears these ahead of time.
    for stray in session.exec(
        select(Doc).where(Doc.parent_doc_id == doc_id, Doc.project_id != project_id)
    ).all():
        stray.parent_doc_id = None
        session.add(stray)

    # Flush child updates/deletes before the doc's own DELETE (parent_doc_id FK).
    session.flush()
    session.delete(doc)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="doc",
        entity_id=doc_id,
        project_id=project_id,
    )
    session.commit()
    return True


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_doc_markdown(session: Session, doc_id: str) -> DocExportResponse:
    doc = session.get(Doc, doc_id)
    if doc is None:
        raise NotFoundError(f"Doc {doc_id!r} not found")

    project = session.get(Project, doc.project_id)
    if project is None:
        raise TypeError("Project not found; cannot export")
    root = resolve_project_root_or_none(project)  # recheck-before-op (#115)
    if root is None:
        raise TypeError("Project folder_path is not set; cannot export")
    subfolder = _TYPE_SUBFOLDER.get(doc.doc_type, "docs")
    rel_path = f"{subfolder}/{doc.slug}.md"

    content = doc.markdown_cache
    content_bytes = content.encode("utf-8")
    rendered_sum = _checksum(content_bytes)

    with project_lock(root):
        existing_bytes = atomic_io.read_bytes(root, rel_path)
        existing_sum = _checksum(existing_bytes) if existing_bytes is not None else None

        drift_detected = (
            doc.export_checksum is not None
            and existing_sum is not None
            and existing_sum != doc.export_checksum
        )

        if drift_detected:
            # #99: the second inverted raise. Export drift is a conflict — the file
            # exists and disagrees with us — not a missing row. It was a LookupError
            # that `endpoints/docs.py` re-mapped to 409, the same double inversion
            # as the version conflict above.
            raise ConflictError(
                "The exported Markdown file was changed outside Planarus. "
                "Review it before exporting again."
            )

        was_changed = existing_sum != rendered_sum
        if was_changed:
            atomic_io.write_text(root, rel_path, content)

    if was_changed or doc.export_relative_path is None:
        doc.export_relative_path = rel_path
        doc.export_checksum = rendered_sum
        doc.exported_at = now_utc()
        doc.updated_at = now_utc()
        session.add(doc)
        session.flush()
        create_audit_event(
            session,
            event_type="doc_export",
            actor_type="human",
            entity_type="doc",
            entity_id=doc.id,
            project_id=doc.project_id,
            payload_json=json.dumps({"export_path": rel_path, "was_changed": was_changed}),
        )
        session.commit()

    return DocExportResponse(
        export_path=rel_path,
        was_changed=was_changed,
        drift_detected=False,
        checksum=rendered_sum,
    )
