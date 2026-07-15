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

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.fsmemory import atomic_io
from app.fsmemory.locks import project_lock
from app.models.doc import Doc
from app.models.project import Project
from app.schemas.doc import DocCreate, DocExportResponse, DocUpdate
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


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def _slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "doc"


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
        raise ValueError(f"Project {project_id!r} not found")

    base_slug = _slugify(payload.slug or payload.title)
    slug = _unique_slug(session, project_id, base_slug)

    ts = now_utc()
    doc = Doc(
        id=new_id("doc"),
        project_id=project_id,
        parent_doc_id=payload.parent_doc_id,
        title=payload.title,
        slug=slug,
        doc_type=payload.doc_type,
        editor_format="tiptap_json",
        content_json=_EMPTY_CONTENT_JSON,
        markdown_cache="",
        status=payload.status,
        sort_order=payload.sort_order,
        version=1,
        created_at=ts,
        updated_at=ts,
    )
    session.add(doc)
    session.flush()
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
) -> list[Doc]:
    stmt = select(Doc).where(Doc.project_id == project_id)
    if not include_archived:
        stmt = stmt.where(Doc.archived_at.is_(None))  # type: ignore[union-attr]
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
        raise ValueError(f"Doc {doc_id!r} not found")

    if payload.version != doc.version:
        raise LookupError(
            f"Version conflict: expected {payload.version}, got {doc.version}"
        )

    # content_json and markdown_cache must always arrive together.
    if (payload.content_json is None) != (payload.markdown_cache is None):
        raise TypeError("content_json and markdown_cache must be provided together")

    changed = False
    if payload.title is not None:
        doc.title = payload.title
        changed = True
    if payload.doc_type is not None:
        doc.doc_type = payload.doc_type
        changed = True
    if payload.status is not None:
        doc.status = payload.status
        changed = True
    if payload.sort_order is not None:
        doc.sort_order = payload.sort_order
        changed = True
    if payload.parent_doc_id is not None:
        doc.parent_doc_id = payload.parent_doc_id
        changed = True
    if payload.content_json is not None:
        doc.content_json = payload.content_json
        doc.markdown_cache = payload.markdown_cache  # type: ignore[assignment]
        changed = True
    if payload.archived_at is not None:
        doc.archived_at = payload.archived_at
        changed = True

    if changed:
        doc.version = doc.version + 1
        doc.updated_at = now_utc()

    session.add(doc)
    session.flush()
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


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_doc_markdown(session: Session, doc_id: str) -> DocExportResponse:
    doc = session.get(Doc, doc_id)
    if doc is None:
        raise ValueError(f"Doc {doc_id!r} not found")

    project = session.get(Project, doc.project_id)
    if project is None or not project.folder_path:
        raise TypeError("Project folder_path is not set; cannot export")

    root = project.folder_path
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
            raise LookupError(
                "The exported Markdown file was changed outside Approvo. "
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
