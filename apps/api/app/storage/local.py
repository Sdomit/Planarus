"""Local-filesystem storage backend (Phase 10.3) — the default.

This holds the atomic, containment-checked filesystem primitives that previously
lived inline in ``fsmemory/atomic_io``. Behavior is unchanged: writes go to a
same-directory temp file that is flushed, fsync'd, and ``os.replace``d onto the
destination, and every path is validated through ``fsmemory.path_safety`` so a
symlink/junction/traversal can't escape the project root.
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional

from app.fsmemory.path_safety import (
    PathSafetyError,
    is_reparse_point,
    resolve_within,
    safe_makedirs,
)


class LocalFilesystemStorage:
    def _ensure_parent(self, root: str, relative_path: str) -> str:
        rel_dir = os.path.dirname(relative_path.replace("\\", "/"))
        if rel_dir:
            safe_makedirs(root, rel_dir)
        # Re-validate the full target immediately before opening it.
        target = resolve_within(root, relative_path)
        parent = os.path.dirname(target)
        if is_reparse_point(parent):
            raise PathSafetyError(f"parent directory is a reparse point: {parent!r}")
        return target

    def write_bytes(self, root: str, relative_path: str, data: bytes) -> str:
        target = self._ensure_parent(root, relative_path)
        parent = os.path.dirname(target)
        fd, tmp_path = tempfile.mkstemp(dir=parent, prefix=".tmp-", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
            return target
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def read_bytes(self, root: str, relative_path: str) -> Optional[bytes]:
        target = resolve_within(root, relative_path)
        try:
            with open(target, "rb") as fh:
                return fh.read()
        except (FileNotFoundError, IsADirectoryError):
            return None

    def exists(self, root: str, relative_path: str) -> bool:
        return os.path.exists(resolve_within(root, relative_path))

    def ensure_file(self, root: str, relative_path: str) -> str:
        target = self._ensure_parent(root, relative_path)
        if not os.path.exists(target):
            self.write_bytes(root, relative_path, b"")
        return target

    def append_line(self, root: str, relative_path: str, line: str) -> str:
        target = self._ensure_parent(root, relative_path)
        with open(target, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
        return target
