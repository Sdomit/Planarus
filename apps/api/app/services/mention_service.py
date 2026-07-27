"""Derive @mention backlink rows from a doc's `content_json` (#138/plan 23).

Mentions are never authored directly — `doc_service.create_doc`/`update_doc`
and the approval-apply path (`policy/handlers._apply_doc_update`) call
`sync_mentions` inside their own save transaction, in the same spirit as
`markdown_cache`: both are projections of `content_json`, recomputed wholesale
on every save rather than diffed.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.mention import Mention
from app.services.entity_ref import filter_existing_refs

#: Ceiling on distinct mention targets stored for one document. `content_json`
#: is capped at 2 MB / 200k nodes, which still leaves room for ~30k mention
#: nodes — enough that the inserts alone hold a write transaction open for
#: seconds. No real document approaches this; a payload that does is either a
#: generator or an attack, and truncating is the honest response either way.
#: ponytail: a flat cap, not a quota. Targets are sorted before slicing so which
#: ones survive is deterministic rather than set-iteration order.
MAX_MENTIONS_PER_DOC = 1000

#: Cheapest possible pre-filter. A document containing no mention node cannot
#: contain this substring under any JSON encoding of `{"type": "mention"}` —
#: json.dumps always quotes the value, with or without a space after the colon.
#: Lets an Excalidraw canvas (also a Doc, autosaving multi-MB scenes on a 1.5 s
#: debounce, and unable to hold a mention) skip both the second full parse and
#: the tree walk.
_MENTION_MARKER = '"mention"'


def _extract_targets(content_json: str) -> set[tuple[str, str]]:
    """Every unique (target_type, target_id) a `mention` node in the tree names.

    Iterative, like `doc._check_json_shape` and `uri_policy._uri_attributes` —
    the tree comes from a payload already size/depth-bounded by the doc schema,
    but there is no reason to add a third recursive walker to that list.

    Every field is type-checked defensively. The document schema bounds this
    JSON's size, depth and node count; it says nothing about the *shape* of an
    individual node, so `attrs` can be whatever a client, an import, or an
    approved agent patch put there.
    """
    try:
        parsed = json.loads(content_json)
    except (TypeError, ValueError):
        return set()

    targets: set[tuple[str, str]] = set()
    stack = [parsed]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") == "mention":
                attrs = node.get("attrs")
                # `or {}` rescued only the *falsy* shapes. A truthy non-dict —
                # a list, a string, a number, `true` — reached .get() and raised
                # AttributeError out of the save: a 500 that discarded the
                # user's edit, and that recurred on every later save once such a
                # node had been stored by an import or an approved patch.
                if isinstance(attrs, dict):
                    target_type = attrs.get("targetType")
                    target_id = attrs.get("targetId")
                    if (
                        isinstance(target_type, str)
                        and isinstance(target_id, str)
                        and target_type
                        and target_id
                    ):
                        targets.add((target_type, target_id))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return targets


def sync_mentions(
    session: Session, project_id: str, source_doc_id: str, content_json: str
) -> None:
    """Full-replace `source_doc_id`'s mention rows from its current `content_json`.

    Call inside the same transaction as the doc save that changed the content —
    does not commit. A target that does not resolve (wrong project, deleted,
    unknown type) is silently skipped, mirroring how a dangling reference is
    handled everywhere else here: annotate on read, never let a stale attachment
    block a save that would otherwise succeed.
    """
    # Unconditional — a doc whose mentions were all removed must lose its rows,
    # so the delete cannot sit behind the early-out below.
    for row in session.exec(
        select(Mention).where(Mention.source_doc_id == source_doc_id)
    ).all():
        session.delete(row)

    if not isinstance(content_json, str) or _MENTION_MARKER not in content_json:
        session.flush()
        return

    targets = sorted(_extract_targets(content_json))[:MAX_MENTIONS_PER_DOC]
    if not targets:
        session.flush()
        return

    ts = now_utc()
    # One query per distinct target *type*, not one per target: see
    # entity_ref.filter_existing_refs.
    for target_type, target_id in sorted(
        filter_existing_refs(session, project_id, targets)
    ):
        session.add(
            Mention(
                id=new_id("men"),
                project_id=project_id,
                source_doc_id=source_doc_id,
                target_type=target_type,
                target_id=target_id,
                created_at=ts,
            )
        )
    session.flush()


def list_mentions(
    session: Session,
    project_id: str,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    source_doc_id: Optional[str] = None,
) -> list[Mention]:
    stmt = select(Mention).where(Mention.project_id == project_id)
    if target_type is not None:
        stmt = stmt.where(Mention.target_type == target_type)
    if target_id is not None:
        stmt = stmt.where(Mention.target_id == target_id)
    if source_doc_id is not None:
        stmt = stmt.where(Mention.source_doc_id == source_doc_id)
    stmt = stmt.order_by(Mention.created_at, Mention.id)
    return list(session.exec(stmt).all())
