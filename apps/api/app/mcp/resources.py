"""MCP resources: whole-document reads (#184).

`get_doc_excerpt` pages a document at MAX_DOC_EXCERPT_CHARS so nothing is
unreachable (#92), but a client still has to page a document it could
otherwise just read. Resources sidestep that for the common case: one
`read_resource` call returns the whole (redacted, boundary-wrapped) document up
to MAX_RESOURCE_CHARS, via the exact same pipeline `get_doc_excerpt` uses
(`read_tools.doc_excerpt_result`) — a resource read is not a lower-scrutiny
path than a tool call.

This module stays SDK-agnostic (the SDK package itself is never imported here)
per the existing convention that only server.py/http_transport.py talk to the
SDK directly; those two files translate a Doc lookup failure raised here into
the transport's own error shape.

Design decision (recorded as a ratified decision, not just a code comment):
resources SIT ALONGSIDE get_doc_excerpt rather than replacing it — get_item and
list_docs are untouched, and a document past MAX_RESOURCE_CHARS still has
get_doc_excerpt's offset paging as the way to read the rest.

One resource TEMPLATE is exposed (not one Resource per document): enumerating
every doc across every scoped project at list_resources() time would need a
`name`/`title` per entry, and a raw doc title is exactly the kind of untrusted
text `serializers.py`'s module contract keeps out of unwrapped protocol
metadata (list_docs already keeps titles inside the wrapped, redacted block,
never in scalar metadata — the resource listing must not quietly reopen that
door). A client already has doc ids from list_docs/get_active_work; it
constructs the URI itself.
"""
from __future__ import annotations

from sqlmodel import Session

from app.mcp.capabilities import Capability
from app.mcp.serializers import MAX_RESOURCE_CHARS
from app.mcp.tools import read as read_tools

DOC_URI_PREFIX = "planarus://doc/"

DOC_RESOURCE_TEMPLATE = {
    "name": "doc",
    "uriTemplate": f"{DOC_URI_PREFIX}{{doc_id}}",
    "description": (
        "One project document, in full (redacted, boundary-wrapped Markdown), "
        "up to a generous character cap. Get doc_id from list_docs or "
        "get_active_work; use get_doc_excerpt to page past the cap."
    ),
    "mimeType": "text/markdown",
}


def parse_doc_id(uri: str) -> str | None:
    """Extract `doc_id` from a `planarus://doc/{doc_id}` URI, else None."""
    if not uri.startswith(DOC_URI_PREFIX):
        return None
    doc_id = uri[len(DOC_URI_PREFIX) :]
    return doc_id or None


def read_doc_resource(session: Session, cap: Capability, doc_id: str) -> str:
    """Return the resource body text. Raises MCPToolError(CODE_NOT_FOUND) for a
    missing or out-of-scope doc — identical to get_doc_excerpt's own generic
    not-found, so a resource read cannot be used to enumerate doc existence
    across projects the caller cannot see."""
    result = read_tools.doc_excerpt_result(
        session, cap, doc_id, MAX_RESOURCE_CHARS, offset=0
    )
    return result.text
