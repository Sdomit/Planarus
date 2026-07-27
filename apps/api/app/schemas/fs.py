from typing import Optional

from pydantic import BaseModel


class FsDir(BaseModel):
    """One subdirectory in a folder listing. ``is_git`` marks a Git repo root
    (a ``.git`` entry exists inside) so the picker can badge candidate repos."""

    name: str
    path: str
    is_git: bool = False


class FsListing(BaseModel):
    """A directory listing for the local folder picker (Phase 12d).

    Local-mode, local-UI only: the endpoint serving this is control-token gated
    and 409s outright when auth/team mode is enabled, because browsing the
    server's filesystem is a single-user affordance — in team mode project roots
    are server-derived and a tenant never picks an arbitrary path (#115).

    ``roots`` lists the navigation anchors (drives on Windows, ``/`` and home
    elsewhere). ``parent`` is ``None`` at a filesystem root. Unreadable entries
    are silently skipped rather than failing the whole listing.
    """

    path: str
    parent: Optional[str] = None
    is_git: bool = False
    dirs: list[FsDir] = []
    roots: list[str] = []
    message: Optional[str] = None
