"""One URI policy for every stored hyperlink and image source (#118).

Planarus had three policies that disagreed. The notes UI normalized to
``http``/``https``; `LinkCreate` blocked three literal prefixes and explicitly
permitted `file:` and custom schemes; rich-document JSON was checked for syntax
and size and never for what its ``href``/``src`` attributes pointed at. Import
and direct API calls reach none of the frontend checks at all.

So the rule lives here, once, and every writer calls it.

**Links** — ``http``, ``https``, ``mailto``, and (in rich content only) a
document-relative reference. Nothing else: not ``javascript``, not ``data``, not
``file``, not a custom scheme. A stored hyperlink is something a human clicks in
a browser; every other scheme is either an injection vector or a reference to
the *reader's* machine rather than the author's.

**Images** — ``http``/``https``, plus base64 ``data:`` URIs for the raster types
the editor itself produces. Pasting an image into a doc inlines it as a
``data:image/jpeg;base64,...`` (see ``DocsPanel.imageToDataUrl``), so refusing
``data:`` outright would break the paste path that exists today.
``image/svg+xml`` is deliberately **not** in the allowed set: an SVG is a
document, not a raster, and an inline one is a markup surface we would then have
to sanitize.

Remote (``http(s)``) image sources are **allowed on purpose**, and the tradeoff
is explicit: opening a document that carries one makes the reader's browser
issue an outbound request to a third party. That is the cost of the "insert
image by URL" toolbar button. The CSP in ``apps/web/nginx.conf`` is written to
match this exactly — narrowing it there and here must happen together.

Rejections raise ``ValueError``, which the v1 endpoints already surface as 422.
"""
from __future__ import annotations

import re
from typing import Callable, Iterator, Optional
from urllib.parse import urlsplit

#: A hyperlink long enough to exceed this is not a link anyone typed. Matches the
#: existing `LinkCreate.url` field cap so the two can never disagree.
MAX_LINK_LENGTH = 2000

_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
_IMAGE_SCHEMES = frozenset({"http", "https"})

#: Raster types the editor can produce or a human would reasonably paste.
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp|avif);base64,[A-Za-z0-9+/=]+$")

# Characters a browser strips or reinterprets *before* it decides what scheme a
# URL has, which is exactly how `java<TAB>script:alert(1)` gets past a naive
# prefix check. Rather than replicate the browser's stripping, refuse any URL
# that contains one — no legitimate stored URL does. Written as escapes on
# purpose: most of these are invisible, and a literal one in this pattern would
# be exactly the bug the pattern exists to stop.
_FORBIDDEN_CHARS = re.compile(
    "["
    "\\x00-\\x20"  # C0 controls and space
    "\\x7f-\\x9f"  # DEL and C1 controls
    "\\\\"  # backslash: browsers read it as "/", urlsplit does not, so the
    #          two disagree about where the host ends
    "\\u200b-\\u200f"  # zero-width space/joiner, LTR/RTL marks
    "\\u2028\\u2029"  # line and paragraph separators
    "\\u202a-\\u202e"  # bidi embedding and override
    "\\u2066-\\u2069"  # bidi isolates
    "\\ufeff"  # BOM / zero-width no-break space
    "]"
)

_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")

#: Attribute names that carry a hyperlink in Tiptap JSON (`href` on the link
#: mark) or an Excalidraw scene (`link` on any element). `action`/`formaction`
#: are not produced by either editor and are here because they are what a crafted
#: payload would reach for if a future renderer ever passed attributes through.
_LINK_KEYS = frozenset({"href", "url", "link", "action", "formaction", "xlink:href", "poster"})

#: Attribute names that carry an image source: `src` on the Tiptap image node,
#: `dataURL` on an Excalidraw binary file entry (keys are matched lowercased).
_IMAGE_KEYS = frozenset({"src", "dataurl", "background"})

_URI_KEYS = _LINK_KEYS | _IMAGE_KEYS


def _reject_shape(raw: str, label: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError(f"{label} is empty")
    bad = _FORBIDDEN_CHARS.search(value)
    if bad:
        raise ValueError(
            f"{label} contains a forbidden character (U+{ord(bad.group()):04X})"
        )
    return value


def _scheme_of(value: str) -> Optional[str]:
    m = _SCHEME.match(value)
    return m.group(1).lower() if m else None


def _check_authority(value: str, label: str) -> None:
    """Reject credentials and malformed hosts in an http(s) URL."""
    parts = urlsplit(value)
    if parts.username or parts.password:
        # `https://trusted.example@evil.test/` reads as trusted.example to a human
        # and resolves to evil.test. There is no legitimate reason to store one.
        raise ValueError(f"{label} must not carry credentials")
    try:
        host = parts.hostname
    except ValueError:  # urlsplit rejects some malformed IPv6 authorities
        raise ValueError(f"{label} has a malformed host") from None
    if not host:
        raise ValueError(f"{label} has no host")
    if host.startswith((".", "-")) or host.endswith((".", "-")) or ".." in host:
        raise ValueError(f"{label} has a malformed host")


def normalize_link(raw: str, *, label: str = "url", allow_relative: bool = False) -> str:
    """Return the stored form of a hyperlink, or raise ``ValueError``.

    ``allow_relative`` is on for rich-document content, where a reference like
    ``#section`` or ``/docs/x`` resolves against the app's own origin and is
    therefore no more dangerous than any in-app navigation. It is off for `Link`
    rows, which are bookmarks to somewhere else and are meaningless relative to
    an origin the reader may not share.
    """
    value = _reject_shape(raw, label)
    if len(value) > MAX_LINK_LENGTH:
        raise ValueError(f"{label} is longer than {MAX_LINK_LENGTH} characters")

    scheme = _scheme_of(value)
    if scheme is None:
        if not allow_relative:
            raise ValueError(f"{label} must be an absolute http(s) or mailto URL")
        # A scheme-relative `//evil.test` inherits the page's scheme: a remote URL
        # wearing a relative URL's clothes.
        if value.startswith("//"):
            raise ValueError(f"{label} must not be scheme-relative")
        if not value.startswith(("/", "./", "../", "#", "?")):
            raise ValueError(f"{label} is not a recognized relative reference")
        return value

    if scheme not in _LINK_SCHEMES:
        raise ValueError(f"{label} scheme '{scheme}:' is not allowed")
    if scheme == "mailto":
        if "@" not in value[len("mailto:"):]:
            raise ValueError(f"{label} is not a valid mailto address")
        return value
    _check_authority(value, label)
    return value


def normalize_image_src(raw: str, *, label: str = "src", allow_relative: bool = True) -> str:
    """Return the stored form of an image source, or raise ``ValueError``."""
    value = _reject_shape(raw, label)
    scheme = _scheme_of(value)
    if scheme is None:
        if not allow_relative:
            raise ValueError(f"{label} must be an absolute URL")
        if value.startswith("//"):
            raise ValueError(f"{label} must not be scheme-relative")
        if not value.startswith(("/", "./", "../")):
            raise ValueError(f"{label} is not a recognized relative reference")
        return value
    if scheme == "data":
        if not _DATA_IMAGE.match(value):
            raise ValueError(
                f"{label} must be a base64 data URI of type png, jpeg, gif, webp or avif"
            )
        return value
    if scheme not in _IMAGE_SCHEMES:
        raise ValueError(f"{label} scheme '{scheme}:' is not allowed")
    if len(value) > MAX_LINK_LENGTH:
        raise ValueError(f"{label} is longer than {MAX_LINK_LENGTH} characters")
    _check_authority(value, label)
    return value


def _uri_attributes(value: object, field: str) -> Iterator[tuple[Callable, str, str]]:
    """Yield ``(checker, value, label)`` for every URI attribute in a JSON tree.

    Deliberately keyed on *attribute name* rather than on the Tiptap or
    Excalidraw node schema. Both schemas are owned upstream and both change; a
    validator pinned to one of them fails open the first time a version adds a
    node, which is the wrong direction to fail. Every URI either of them stores
    lands under one of a small, stable set of attribute names, and anything under
    one of those names is checked no matter which node it hangs off.

    Iterative for the same reason `doc._check_json_shape` is: the input is
    hostile by assumption, and a recursive walk would blow the stack on exactly
    the payload it exists to reject.
    """
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, item in node.items():
                lowered = key.lower() if isinstance(key, str) else ""
                if isinstance(item, str) and item.strip() and lowered in _URI_KEYS:
                    checker = normalize_link if lowered in _LINK_KEYS else normalize_image_src
                    yield checker, item, f"{field}.{key}"
                else:
                    stack.append(item)
        elif isinstance(node, list):
            stack.extend(node)


def check_rich_content(value: object, field: str) -> None:
    """Raise on the first URI attribute in a parsed rich document this policy rejects."""
    for checker, item, label in _uri_attributes(value, field):
        checker(item, label=label, allow_relative=True)


def rich_content_violations(value: object, field: str = "content_json") -> list[str]:
    """Every URI in ``value`` this policy rejects, as messages. Empty means clean."""
    problems: list[str] = []
    for checker, item, label in _uri_attributes(value, field):
        try:
            checker(item, label=label, allow_relative=True)
        except ValueError as exc:
            problems.append(str(exc))
    return problems


def is_allowed_link(raw: str, *, allow_relative: bool = False) -> bool:
    """Non-raising form, for auditing rows written before this policy existed."""
    try:
        normalize_link(raw, allow_relative=allow_relative)
        return True
    except ValueError:
        return False
