"""Path-containment guards for generated project-folder writes.

Every path the fsmemory layer opens passes through `resolve_within`, which
canonicalises a relative candidate against a project root and refuses anything
that escapes it: `..` traversal, absolute paths, drive/UNC/device prefixes,
NTFS alternate-data-stream (`:`) components, and symlink/junction/reparse-point
escapes. Containment is decided with `os.path.commonpath` on *realpath*-resolved
paths — never a string-prefix comparison — so a symlink or Windows junction in
any existing path component is resolved and re-checked before it can be used.

`os.path.realpath` resolves symlinks and Windows junctions/reparse points
(CPython 3.8+), which is the core of the symlink/junction defence.
"""
from __future__ import annotations

import os
import stat

# FILE_ATTRIBUTE_REPARSE_POINT — symlinks, junctions, and other reparse points
# on Windows. `stat` exposes the constant on Windows; fall back to the literal.
_REPARSE_ATTR = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class PathSafetyError(ValueError):
    """A candidate path is not safely contained within the project root."""


def is_reparse_point(path: str) -> bool:
    """True if `path` is a symlink (POSIX) or a reparse point/junction (Windows)."""
    try:
        st = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError):
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & _REPARSE_ATTR)


def _reject_suspicious_relpath(relative_path: str) -> None:
    """Reject obviously-unsafe relative paths before any filesystem touch."""
    if not isinstance(relative_path, str) or not relative_path:
        raise PathSafetyError(f"empty path: {relative_path!r}")
    if relative_path != relative_path.strip():
        raise PathSafetyError(f"untrimmed path: {relative_path!r}")
    if "\x00" in relative_path:
        raise PathSafetyError("null byte in path")
    # Device / UNC prefixes (check before separator normalisation).
    if relative_path.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\")):
        raise PathSafetyError(f"device/UNC path not allowed: {relative_path!r}")
    norm = relative_path.replace("\\", "/")
    if norm.startswith("/"):
        raise PathSafetyError(f"absolute path not allowed: {relative_path!r}")
    for part in norm.split("/"):
        if part in ("", ".", ".."):
            raise PathSafetyError(f"path traversal not allowed: {relative_path!r}")
        if ":" in part:
            # Drive letters ("C:") and NTFS alternate data streams ("f:stream").
            raise PathSafetyError(f"colon not allowed in path: {relative_path!r}")


def resolve_root(root: str) -> str:
    """Validate and canonicalise a project root. Must be an absolute directory."""
    if not isinstance(root, str) or not root:
        raise PathSafetyError(f"empty project root: {root!r}")
    if "\x00" in root:
        raise PathSafetyError("null byte in project root")
    if not os.path.isabs(root):
        raise PathSafetyError(f"project root must be absolute: {root!r}")
    return os.path.realpath(root)


def resolve_within(root: str, relative_path: str) -> str:
    """Return the absolute, containment-checked path for `relative_path`.

    Raises `PathSafetyError` if the candidate escapes `root` by any means. Safe
    to call repeatedly — callers re-invoke it immediately before opening a file
    to minimise the TOCTOU window.
    """
    _reject_suspicious_relpath(relative_path)
    root_real = resolve_root(root)

    native_rel = relative_path.replace("/", os.sep)
    candidate = os.path.join(root_real, native_rel)
    # realpath resolves symlinks/junctions in whatever prefix already exists and
    # appends the not-yet-existing tail literally.
    candidate_real = os.path.realpath(candidate)

    try:
        common = os.path.commonpath([root_real, candidate_real])
    except ValueError as exc:
        # Raised when paths are on different drives (Windows) — definitely outside.
        raise PathSafetyError(
            f"path is not under the project root: {relative_path!r}"
        ) from exc
    if os.path.normcase(common) != os.path.normcase(root_real):
        raise PathSafetyError(f"path escapes project root: {relative_path!r}")

    # Defence in depth: if any existing component along the way is a reparse
    # point whose target leaves the root, deny — even if realpath happened to
    # land back inside.
    _assert_no_reparse_escape(root_real, candidate_real)
    return candidate_real


def _assert_no_reparse_escape(root_real: str, candidate_real: str) -> None:
    current = candidate_real
    root_nc = os.path.normcase(root_real)
    while True:
        if is_reparse_point(current):
            resolved = os.path.realpath(current)
            try:
                common = os.path.commonpath([root_real, resolved])
            except ValueError as exc:
                raise PathSafetyError(
                    f"reparse point escapes project root: {current!r}"
                ) from exc
            if os.path.normcase(common) != root_nc:
                raise PathSafetyError(
                    f"reparse point escapes project root: {current!r}"
                )
        if os.path.normcase(current) == root_nc:
            break
        parent = os.path.dirname(current)
        if parent == current:  # reached a filesystem root without hitting root_real
            break
        current = parent


def safe_makedirs(root: str, relative_dir: str) -> str:
    """Create `relative_dir` (and parents) under `root`, containment-checked.

    Returns the canonical directory path. A no-op if it already exists. Refuses
    to create through a reparse point that escapes the root.
    """
    target = resolve_within(root, relative_dir)
    os.makedirs(target, exist_ok=True)
    # Re-validate now that the directory exists (realpath fully resolves it).
    resolve_within(root, relative_dir)
    return target
