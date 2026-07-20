from typing import Optional

from pydantic import BaseModel


class BackupFile(BaseModel):
    """One backup file on disk.

    Name only — the backup directory is server config (an env ceiling), so the
    absolute path is never disclosed, matching the "never leak paths" rule the
    external surfaces already follow.
    """

    name: str
    size_bytes: int
    created_at: str


class BackupResult(BaseModel):
    """Outcome of one "back up now" run."""

    backup: BackupFile
    pruned: int  # older backups removed by the retention setting
    # P18.4 (D44): where the off-site copy landed, when that switch is on. The
    # push is best-effort — the verified local file is the deliverable and
    # already exists — so a failure is *reported here*, never raised. Reporting
    # the reason is what separates a known-degraded backup from a silent one.
    offsite: Optional[str] = None
    offsite_error: Optional[str] = None


class RestoreResult(BaseModel):
    """Outcome of a CLI restore (D43 — never an HTTP route). Names only, for the
    same reason BackupFile carries no path."""

    restored_from: str
    database: str
    # The displaced live database + any -wal/-shm sidecars, kept as
    # ".pre-restore-<stamp>" copies so a mistaken restore is reversible.
    displaced: list[str]
