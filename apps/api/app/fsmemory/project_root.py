"""Server-side ownership of a project's filesystem root (issue #115).

`path_safety` guards the *children written within* a root; this module guards the
*root itself* — the trust boundary that layer cannot enforce.

- **Auth-enabled (multi-user) mode:** the root is server-owned and derived from
  immutable ids as ``<PLANARUS_PROJECTS_ROOT>/<workspace_id>/<project_id>``. A
  tenant may not choose it, and every filesystem/git operation recomputes it
  from ids rather than trusting the stored string.
- **Local single-user mode:** the operator may still pass an absolute root (an
  explicit, documented escape hatch), but obviously-dangerous roots (a
  filesystem/drive root, a system directory, the application directory) and
  overlapping roots are rejected in both modes.

`resolve_project_root(project)` is the one chokepoint every consumer must call
before touching disk.
"""
from __future__ import annotations

import os
from typing import Optional

from app.core.config import settings
from app.fsmemory.path_safety import PathSafetyError, resolve_root


class ProjectRootError(ValueError):
    """A project root is not acceptable: unowned, dangerous, or overlapping."""


# Directories we refuse to provision into even in the local escape hatch. Auth
# mode never reaches this list (its root is always derived under the base), so
# this is defence-in-depth for a fat-fingered local absolute path.
_SYSTEM_DIRS = frozenset(
    os.path.normcase(p)
    for p in (
        "/", "/etc", "/var", "/usr", "/bin", "/sbin", "/lib", "/lib64",
        "/boot", "/dev", "/proc", "/sys", "/run", "/root", "/home",
        "C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
        "C:\\Users",
    )
)


def _app_dir() -> str:
    """The application install directory (…/apps/api), canonicalised."""
    return os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def roots_overlap(a: str, b: str) -> bool:
    """True if two absolute roots are equal or one contains the other.

    Both are realpath-resolved and compared with ``commonpath`` (never a string
    prefix), so ``/x`` and ``/x2`` do not falsely overlap while ``/x`` and
    ``/x/sub`` do.
    """
    a_real, b_real = os.path.realpath(a), os.path.realpath(b)
    try:
        common = os.path.normcase(os.path.commonpath([a_real, b_real]))
    except ValueError:
        return False  # different drives — cannot overlap
    return common in (os.path.normcase(a_real), os.path.normcase(b_real))


def assert_not_dangerous(root_real: str) -> None:
    """Reject filesystem/drive roots, known system dirs, and the app directory."""
    nc = os.path.normcase(root_real)
    if os.path.dirname(root_real) == root_real:
        raise ProjectRootError(f"refusing a filesystem/drive root: {root_real!r}")
    if nc in _SYSTEM_DIRS:
        raise ProjectRootError(f"refusing a system directory: {root_real!r}")
    if roots_overlap(root_real, _app_dir()):
        raise ProjectRootError(f"refusing the application directory: {root_real!r}")


def managed_base() -> str:
    """The configured server-owned base, canonicalised. Raises if unset."""
    base = settings.projects_root
    if not base:
        raise ProjectRootError("PLANARUS_PROJECTS_ROOT is not configured")
    return resolve_root(base)


def managed_root_for(workspace_id: str, project_id: str) -> str:
    """Canonical server-owned root for a project: ``<base>/<ws>/<proj>``.

    Ids are immutable and server-generated, so the layout is non-overlapping by
    construction. Ids are still shape-checked (no separators/traversal) so a
    hypothetical bad id can never widen the path.
    """
    for part in (workspace_id, project_id):
        if (
            not part
            or "/" in part
            or "\\" in part
            or "\x00" in part
            or part in (".", "..")
        ):
            raise ProjectRootError(f"unsafe id component for a managed root: {part!r}")
    base = managed_base()
    root = os.path.realpath(os.path.join(base, workspace_id, project_id))
    try:
        common = os.path.normcase(os.path.commonpath([base, root]))
    except ValueError as exc:
        raise ProjectRootError("derived root escapes the projects base") from exc
    if common != os.path.normcase(base):
        raise ProjectRootError("derived root escapes the projects base")
    return root


def validate_local_root(candidate: str) -> str:
    """Canonicalise and vet an operator-supplied local root (escape hatch).

    Overlap with *other projects* is enforced by the service layer (it needs the
    DB); this covers the DB-free checks: absolute, non-dangerous.
    """
    root = resolve_root(candidate)  # absolute + realpath; raises PathSafetyError
    assert_not_dangerous(root)
    return root


def resolve_project_root(project) -> str:
    """Return the validated absolute root for a project, or raise.

    The single chokepoint for every filesystem/git consumer. Never trusts the
    stored string blindly: in auth mode it recomputes the canonical path from
    ids on every call; in local mode it re-vets the stored path.
    """
    if settings.auth_enabled:
        return managed_root_for(project.workspace_id, project.id)
    if not project.folder_path:
        raise ProjectRootError(f"project {project.id} has no folder_path")
    return validate_local_root(project.folder_path)


def resolve_project_root_or_none(project) -> Optional[str]:
    """Like ``resolve_project_root`` but returns ``None`` instead of raising.

    For read-only consumers (git/gh cockpit, context reads) that treat a
    missing, folderless, or newly-invalid root as "no data" rather than an
    error — and so must never run against a root that no longer validates.
    """
    try:
        return resolve_project_root(project)
    except (ProjectRootError, PathSafetyError):
        return None
