"""In-memory storage backend (Phase 10.3).

For tests and ephemeral/hosted-preview use — nothing touches disk. Objects are
addressed by a normalized ``root\\x00relative_path`` key. It enforces its own
key-safety (rejecting ``..`` traversal and absolute relative paths) since the
POSIX symlink/realpath model of the local backend doesn't apply to a keyspace.
This is also the shape a real object-store (S3/GCS) adapter follows.
"""
from __future__ import annotations

from typing import Optional

from app.storage.base import StorageError


def _safe_key(root: str, relative_path: str) -> str:
    raw = relative_path.replace("\\", "/")
    # An absolute relative_path would escape the root keyspace — the local backend
    # rejects it via resolve_within, so the memory backend must too.
    if raw.startswith("/"):
        raise StorageError(f"relative_path must not be absolute: {relative_path!r}")
    rel = raw.strip("/")
    parts = rel.split("/")
    if not rel or any(p in ("", ".", "..") for p in parts):
        raise StorageError(f"unsafe relative path: {relative_path!r}")
    return f"{root}\x00{rel}"


class InMemoryStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def write_bytes(self, root: str, relative_path: str, data: bytes) -> str:
        key = _safe_key(root, relative_path)
        self._objects[key] = bytes(data)
        return f"mem://{root}/{relative_path.replace(chr(92), '/').strip('/')}"

    def read_bytes(self, root: str, relative_path: str) -> Optional[bytes]:
        return self._objects.get(_safe_key(root, relative_path))

    def exists(self, root: str, relative_path: str) -> bool:
        return _safe_key(root, relative_path) in self._objects

    def ensure_file(self, root: str, relative_path: str) -> str:
        key = _safe_key(root, relative_path)
        if key not in self._objects:
            self._objects[key] = b""
        return f"mem://{root}/{relative_path.replace(chr(92), '/').strip('/')}"

    def append_line(self, root: str, relative_path: str, line: str) -> str:
        key = _safe_key(root, relative_path)
        self._objects[key] = self._objects.get(key, b"") + line.encode("utf-8")
        return f"mem://{root}/{relative_path.replace(chr(92), '/').strip('/')}"
