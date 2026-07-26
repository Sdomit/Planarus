"""Bounded, redacted, injection-safe serialization of project content for MCP.

All MCP output may be fed to another model, so project text is treated as
untrusted reference material: it is secret-masked, length-clipped, defanged, and
wrapped in source-labelled boundary markers, and the response begins with the
mandatory precedence sentence. Safe scalar metadata (ids, statuses, counts,
flags) is kept separate from the wrapped text — raw titles/descriptions/decisions
never appear in metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.utils import estimate_tokens
from app.prompt import boundary

# Reuse the Phase 6A secret-detection patterns so what we *detect* is exactly what
# we *mask* (secrets.py is read-only this phase; this is deliberate shared reuse,
# not a re-implementation). Only the smallest masking wrapper is added here.
from app.prompt.secrets import (  # noqa: PLC2701 — intentional internal reuse
    _ENTROPY_THRESHOLD,
    _HIGH_ENTROPY_CANDIDATE,
    _shannon_entropy,
)
from app.prompt.secrets import (
    _PATTERNS as _SECRET_PATTERNS,
)

MAX_LIST_ROWS = 100
MAX_FIELD_CHARS = 500
MAX_DOC_EXCERPT_CHARS = 4000
# #92: the cap for a single-item detail read. List rows stay clipped at
# MAX_FIELD_CHARS to bound a 100-row page; before get_item there was no tool at
# any larger cap, so an agent told "truncated, 1400 more chars" had no way to
# read the rest and would propose an update from the first 500 characters.
MAX_DETAIL_CHARS = 4000

_PLACEHOLDER = "«redacted:{label}»"


@dataclass
class ToolResult:
    """metadata: safe scalars only. text: precedence sentence + wrapped content."""

    metadata: dict
    text: str


def redact(text: str) -> tuple[str, list[str]]:
    """Mask secret-like spans; return (clean_text, sorted_unique_labels)."""
    labels: list[str] = []
    result = text
    for label, pattern in _SECRET_PATTERNS:
        def _sub(m, _label=label):
            labels.append(_label)
            return _PLACEHOLDER.format(label=_label)

        result = pattern.sub(_sub, result)

    def _he(m):
        s = m.group(0)
        if _shannon_entropy(s) >= _ENTROPY_THRESHOLD:
            labels.append("high-entropy-string")
            return _PLACEHOLDER.format(label="high-entropy-string")
        return s

    result = _HIGH_ENTROPY_CANDIDATE.sub(_he, result)
    return result, sorted(set(labels))


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f" …(truncated, {len(text) - limit} more chars)", True


def _render_field(label: str, value: object, limit: int):
    """Return (line, secret_labels, suspicious_flags, truncated) for one field.

    Redaction runs on the FULL value BEFORE clipping, so a secret straddling the
    truncation boundary is masked (the surviving fragment can't slip through). The
    clip then trims already-masked text (placeholders are short and never split a
    real secret).
    """
    if value is None or value == "":
        return f"{label}: (none)", [], [], False
    raw = str(value)
    flags = boundary.find_suspicious(raw)
    masked, secrets = redact(raw)
    clipped, truncated = _clip(masked, limit)
    return f"{label}: {clipped}", secrets, flags, truncated


@dataclass
class Block:
    lines: list[str]
    secret_labels: list[str]
    flags: list[str]
    truncated: bool


def wrap_block(
    source_id: str,
    kind: str,
    scalar_lines: list[str],
    text_fields: list[tuple[str, object, int]],
) -> Block:
    """Build one boundary-wrapped, redacted block for an entity."""
    body = list(scalar_lines)
    secret_labels: list[str] = []
    flags: list[str] = []
    truncated = False
    for label, value, limit in text_fields:
        line, sl, fl, t = _render_field(label, value, limit)
        body.append(line)
        secret_labels += sl
        flags += fl
        truncated = truncated or t
    return Block(
        lines=boundary.wrap_source(source_id, kind, body),
        secret_labels=sorted(set(secret_labels)),
        flags=sorted(set(flags)),
        truncated=truncated,
    )


def build_result(metadata: dict, blocks: list[Block]) -> ToolResult:
    """Assemble the final ToolResult: precedence sentence first, then blocks.

    Aggregated secret/flag labels and the approximate token count are added to
    metadata as label lists / scalars only (never raw content).
    """
    lines: list[str] = [boundary.PRECEDENCE_SENTENCE, ""]
    secret_labels: list[str] = []
    flags: list[str] = []
    truncated = False
    for b in blocks:
        lines += b.lines + [""]
        secret_labels += b.secret_labels
        flags += b.flags
        truncated = truncated or b.truncated
    text = "\n".join(lines).rstrip() + "\n"

    # Defence-in-depth: rescan the fully assembled text so a boundary straddle or
    # any future ordering regression cannot ship an unmasked secret to stdout.
    text, leaked = redact(text)
    secret_labels += leaked

    md = dict(metadata)
    if secret_labels:
        md["secret_findings"] = sorted(set(secret_labels))
    if flags:
        md["injection_flags"] = sorted(set(flags))
    md["field_truncated"] = truncated
    md["approximate_token_estimate"] = estimate_tokens(text)
    return ToolResult(metadata=md, text=text)


def status_only_result(metadata: dict, note: Optional[str] = None) -> ToolResult:
    """For tools with no untrusted content (e.g. get_approval_status)."""
    text = boundary.PRECEDENCE_SENTENCE + "\n"
    if note:
        text += "\n" + note + "\n"
    return ToolResult(metadata=dict(metadata), text=text)
