import hashlib
import uuid
from datetime import datetime, timezone


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def sha256_hex(text: str) -> str:
    """Hex SHA-256 of `text` (UTF-8). Used for content-derived checksums."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Approximate token count — a documented heuristic, NOT a real tokenizer.

    Uses ~4 characters per token, the common rough ratio for mixed English prose
    and code. Deterministic and dependency-free (no external tokenizer API). The
    real per-model tokenizers (Claude, GPT/Codex) differ by roughly 10-20%, so
    every value surfaced from this is labelled "approximate" and budgets carry a
    safety margin. Empty text is 0 tokens; any non-empty text is at least 1.
    """
    if not text:
        return 0
    return max(1, -(-len(text) // 4))  # ceil(len / 4)
