"""Local folder browsing for the repo/folder picker (Phase 12d).

One read-only endpoint that lists directories on the machine the API runs on,
so the local UI can offer Browse instead of demanding a hand-typed absolute
path. Deliberately narrow:

- Directories only — never file names, sizes or contents.
- Local mode only — 409 when auth/team mode is on (browsing the server's
  filesystem is a single-user affordance; hosted project roots are
  server-derived per #115) — and control-token gated like the other
  local-control surfaces, so a LAN page cannot enumerate folders.
- Hidden and system entries are skipped; unreadable entries are skipped
  instead of failing the listing.
"""
import os
import string
import sys

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.security import require_local_control
from app.schemas.fs import FsDir, FsListing

router = APIRouter()


def _roots() -> list[str]:
    if sys.platform == "win32":
        return [
            f"{letter}:\\"
            for letter in string.ascii_uppercase
            if os.path.isdir(f"{letter}:\\")
        ]
    return ["/", os.path.expanduser("~")]


def _is_git(path: str) -> bool:
    # .git may be a directory or a worktree/submodule pointer file.
    return os.path.exists(os.path.join(path, ".git"))


@router.get(
    "/fs/dirs",
    response_model=FsListing,
    dependencies=[Depends(require_local_control)],
)
def list_dirs(path: str | None = None) -> FsListing:
    """List the subdirectories of ``path`` (default: the user's home folder)."""
    if settings.auth_enabled:
        raise ConflictError(
            "filesystem browsing is a local single-user surface and is "
            "disabled in team/hosted mode"
        )

    target = os.path.abspath(os.path.expanduser(path.strip())) if path and path.strip() else os.path.expanduser("~")
    roots = _roots()

    if not os.path.isdir(target):
        return FsListing(
            path=target, roots=roots, message="Folder does not exist or is not readable."
        )

    parent = os.path.dirname(target.rstrip("\\/"))
    at_root = os.path.abspath(parent) == target or not parent

    dirs: list[FsDir] = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if entry.name.startswith(".") or entry.name.startswith("$"):
                    continue
                dirs.append(
                    FsDir(name=entry.name, path=entry.path, is_git=_is_git(entry.path))
                )
    except OSError:
        return FsListing(
            path=target, parent=None if at_root else parent, roots=roots,
            message="Folder could not be read.",
        )

    dirs.sort(key=lambda d: d.name.lower())
    return FsListing(
        path=target,
        parent=None if at_root else parent,
        is_git=_is_git(target),
        dirs=dirs,
        roots=roots,
    )
