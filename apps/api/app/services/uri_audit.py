"""Report stored URIs written before the #118 policy existed.

Every *new* write is now refused by `app.core.uri_policy`, but rows already in
the database were accepted under the old rules — `LinkCreate` explicitly
permitted `file:` and custom schemes, and rich-document JSON was never checked at
all. This finds them.

**It reports and never writes**, which is a deliberate choice rather than an
unfinished one. The two available repairs are both worse than the alternative:
deleting a `Link` row destroys a bookmark whose only sin is a scheme we stopped
accepting, and blanking an `href` inside a document silently edits someone's
writing. So the renderer refuses to make a rejected URI clickable — it degrades
to plain text (`EntityNotes`, `markdown.parseInline`, the Tiptap `isAllowedUri`
policy) — and the row stays intact and visible for a human to fix or keep.

    python -m app.jobs audit-uris
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.uri_policy import is_allowed_link, rich_content_violations
from app.models.doc import Doc
from app.models.link import Link

#: Enough offending rows to act on without printing an entire database back.
MAX_REPORTED = 200


def audit_stored_uris(session: Session) -> dict:
    """Every stored URI the current policy rejects. ``{"links": [...], "docs": [...]}``."""
    links: list[dict] = []
    for link in session.exec(select(Link).order_by(Link.created_at, Link.id)).all():
        if not is_allowed_link(link.url):
            links.append({"id": link.id, "project_id": link.project_id, "url": link.url})
        if len(links) >= MAX_REPORTED:
            break

    docs: list[dict] = []
    for doc in session.exec(select(Doc).order_by(Doc.created_at, Doc.id)).all():
        if not doc.content_json:
            continue
        try:
            parsed = json.loads(doc.content_json)
        except ValueError:
            # Unparseable content predates the #117 syntax check; it renders as an
            # empty document rather than as a link, so it is not a URI finding.
            continue
        problems = rich_content_violations(parsed)
        if problems:
            docs.append(
                {
                    "id": doc.id,
                    "project_id": doc.project_id,
                    "title": doc.title,
                    "problems": problems[:10],
                }
            )
        if len(docs) >= MAX_REPORTED:
            break

    return {"links": links, "docs": docs, "total": len(links) + len(docs)}
