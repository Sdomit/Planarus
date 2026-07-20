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


class RestoreResult(BaseModel):
    """Outcome of a CLI restore (D43 — never an HTTP route). Names only, for the
    same reason BackupFile carries no path."""

    restored_from: str
    database: str
    # The displaced live database + any -wal/-shm sidecars, kept as
    # ".pre-restore-<stamp>" copies so a mistaken restore is reversible.
    displaced: list[str]
