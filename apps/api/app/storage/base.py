"""Storage backend protocol (Phase 10.3).

Backends are keyed by ``(root, relative_path)`` — the same addressing the fsmemory
layer already uses (an absolute project-folder root + a forward-slash relative
path). A backend maps that pair onto its medium: a real file for the local
filesystem, an object key for S3, a dict entry for the in-memory backend.

Contract notes:
- ``write_bytes`` MUST be atomic (a crashed write never leaves a half-written
  destination) and MUST create intermediate directories/prefixes.
- ``append_line`` appends one already-terminated line (callers include the
  ``\\n``) to an append-only log.
- ``location`` returns an opaque, medium-specific handle (an absolute path for
  local, a URI/key for object stores). Callers use it only for display or
  local-only features; it is never parsed for portability.
- Every method must reject path traversal / escapes from ``root``.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


class StorageError(Exception):
    """A storage operation failed (bad backend name, unsafe key, I/O error)."""


@runtime_checkable
class Storage(Protocol):
    def write_bytes(self, root: str, relative_path: str, data: bytes) -> str:
        """Atomically write ``data``; return the backend location."""

    def read_bytes(self, root: str, relative_path: str) -> Optional[bytes]:
        """Return the stored bytes, or ``None`` if the object does not exist."""

    def exists(self, root: str, relative_path: str) -> bool:
        """Whether an object exists at ``(root, relative_path)``."""

    def ensure_file(self, root: str, relative_path: str) -> str:
        """Ensure an (empty) object exists without truncating one that already
        does; return its location."""

    def append_line(self, root: str, relative_path: str, line: str) -> str:
        """Append one pre-terminated line to an append-only object; return its
        location."""
