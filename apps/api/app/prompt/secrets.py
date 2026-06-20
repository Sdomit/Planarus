"""Best-effort, local-only secret-pattern detection.

This is a warning aid, NOT a guarantee. It scans text for common secret shapes
and returns only a pattern label, a masked preview, the source reference, and a
count. It NEVER returns or logs a raw secret value. Detection runs on individual
source fragments (so the user knows which source carries a match) and on the
final assembled pack (defence in depth). The UI must present results as
best-effort and must never imply the pack is guaranteed secret-free.

No scanning runs against forbidden paths or `.env*` — those are excluded from
context packs entirely, before this module is ever reached.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretFinding:
    pattern_label: str
    masked_preview: str
    source_ref: str
    count: int


# Ordered, conservative pattern set. `re.finditer` + `group(0)` is used so a
# pattern with sub-groups never leaks a capture group as the matched value.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-header", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
    ),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}")),
    ("authorization-header", re.compile(r"(?i)authorization\s*:\s*\S{8,}")),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|token)"
            r"\s*[=:]\s*['\"]?\S{6,}"
        ),
    ),
    ("dotenv-assignment", re.compile(r"(?m)^[A-Z][A-Z0-9_]{2,}=\S{6,}$")),
)

# High-entropy candidate: a long, contiguous base64/hex-ish run. Checked last and
# gated by a Shannon-entropy threshold to keep false positives low.
_HIGH_ENTROPY_CANDIDATE = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")
_ENTROPY_THRESHOLD = 4.0


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def mask(value: str) -> str:
    """Mask a matched span: keep up to 4 leading chars, replace the rest.

    The leading characters are typically the label word (``password``) or a
    public prefix (``AKIA``), never the secret body. Never returns the raw value.
    """
    v = value.strip()
    if len(v) <= 4:
        return "•" * max(1, len(v))
    return v[:4] + "•" * min(8, max(4, len(v) - 4))


def scan(text: str, source_ref: str) -> list[SecretFinding]:
    """Scan `text`; return one finding per matched label. Never includes raw values."""
    if not text:
        return []
    aggregated: dict[str, dict[str, object]] = {}

    def _record(label: str, raw: str) -> None:
        entry = aggregated.get(label)
        if entry is None:
            aggregated[label] = {"count": 1, "preview": mask(raw)}
        else:
            entry["count"] = int(entry["count"]) + 1

    for label, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            _record(label, m.group(0))

    for m in _HIGH_ENTROPY_CANDIDATE.finditer(text):
        candidate = m.group(0)
        if _shannon_entropy(candidate) >= _ENTROPY_THRESHOLD:
            _record("high-entropy-string", candidate)

    return [
        SecretFinding(
            pattern_label=label,
            masked_preview=str(entry["preview"]),
            source_ref=source_ref,
            count=int(entry["count"]),
        )
        for label, entry in sorted(aggregated.items())
    ]
