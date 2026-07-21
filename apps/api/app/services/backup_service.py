"""Verified local database backups (Phase 18.0 — D42, D44).

SQLite only. ``VACUUM INTO`` writes a **consistent** snapshot of a live WAL
database in a single statement; a plain file copy can capture a torn page set or
miss un-checkpointed WAL frames. The copy is then reopened and checked with
``PRAGMA integrity_check`` before it counts as a backup — an unverified file is
not a backup, so a failed check deletes the file rather than leave something that
merely looks restorable.

Postgres is refused by design (D42): use ``pg_dump`` or the platform's managed
snapshots + point-in-time recovery rather than a hand-rolled dump.

Boundaries:
  * **Off by default** — the ``backup_enabled`` switch gates the whole feature.
  * The destination is an **env ceiling** (``PLANARUS_BACKUP_DIR``), never
    client input; callers cannot choose where bytes land.
  * Retention only ever deletes files matching the generated name pattern —
    anything else living in that directory is left alone.

This is a local-human/CLI operation: it is not reachable from MCP or the external
API, and it emits an audit event whose entity type is deliberately outside
``webhook_service.WEBHOOK_ENTITY_TYPES`` so management activity is never pushed
to an outbound consumer.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.core.config import settings as env
from app.core.exceptions import ConflictError
from app.schemas.backups import BackupFile, BackupResult, RestoreResult
from app.services.audit_service import create_audit_event
from app.services.settings_service import backup_offsite, backup_retention, get_setting

# VACUUM INTO landed in SQLite 3.27 (2019). Checked explicitly so an ancient
# runtime fails with this sentence instead of a bare SQL syntax error.
_MIN_SQLITE = (3, 27, 0)

# The retention default and its floor live in settings_service.backup_retention —
# one source of truth, so a corrupt or out-of-range row behaves identically here.

# planarus-20260719T220501123456Z.db — date, then 12 digits (HHMMSS + micros).
# Microsecond precision makes names unique *and* chronologically sortable, so
# retention can order by filename alone and no collision suffix is needed.
_NAME_RE = re.compile(r"^planarus-\d{8}T\d{12}Z\.db$")


def is_supported(session: Session) -> bool:
    """Whether this database can be backed up by file snapshot (D42)."""
    return (
        session.get_bind().dialect.name == "sqlite"
        and sqlite3.sqlite_version_info >= _MIN_SQLITE
    )


def backup_dir() -> Path:
    return Path(env.backup_dir).expanduser()


def _target(directory: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return directory / f"planarus-{stamp}.db"


def _describe(path: Path) -> BackupFile:
    stat = path.stat()
    return BackupFile(
        name=path.name,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    )


def _integrity_ok(path: Path) -> bool:
    """Whether ``path`` is a SQLite database that passes ``PRAGMA integrity_check``."""
    probe = None
    try:
        probe = sqlite3.connect(path)
        row = probe.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    except sqlite3.Error:
        return False
    finally:
        if probe is not None:
            probe.close()  # Windows: the handle must be closed before unlink/replace


def _verify(path: Path) -> None:
    """Integrity-check a freshly written copy; discard it if it does not pass."""
    if not _integrity_ok(path):
        path.unlink(missing_ok=True)
        raise ConflictError("backup failed its integrity check and was discarded")


def list_backups() -> list[BackupFile]:
    """Existing backups, newest first. Non-matching files are ignored entirely."""
    directory = backup_dir()
    if not directory.is_dir():
        return []
    found = [
        _describe(p)
        for p in directory.iterdir()
        if p.is_file() and _NAME_RE.match(p.name)
    ]
    found.sort(key=lambda b: b.name, reverse=True)
    return found


def _prune(keep: int) -> int:
    """Delete all but the newest ``keep`` backups; return how many were removed."""
    directory = backup_dir()
    removed = 0
    for stale in list_backups()[max(1, keep) :]:
        try:
            (directory / stale.name).unlink()
            removed += 1
        except OSError:
            # A locked or already-vanished file must not fail the backup that
            # just succeeded — retention is housekeeping, not the deliverable.
            pass
    return removed


def _push_offsite(session: Session, path: Path) -> tuple[str | None, str | None]:
    """Best-effort copy of a verified backup to the configured storage backend.

    Returns ``(location, error)`` and **never raises**. The local file is already
    written and integrity-checked, so it *is* the deliverable; failing the whole
    backup because an upload timed out would throw away a good copy. But a silent
    failure is precisely what this phase exists to prevent, so the reason travels
    back in the result rather than being swallowed.
    """
    if not backup_offsite(session):
        return None, None
    if env.storage_backend == "local":
        return None, (
            "off-site copy skipped: the storage backend is 'local', which would "
            "write the copy beside the original. Use the s3 backend, or point "
            "PLANARUS_BACKUP_DIR at a synced folder instead."
        )
    try:
        # Local import: the s3 backend pulls boto3, an optional extra — keep it
        # off the import path of every deployment that never pushes anything.
        from app.storage import get_storage

        # ponytail: reads the whole file into memory. Fine for a local project DB
        # (megabytes); switch to a streaming/multipart upload if these grow.
        location = get_storage().write_bytes(
            str(path.parent), path.name, path.read_bytes()
        )
        return location, None
    except Exception as exc:  # noqa: BLE001 — a good local backup must survive this
        return None, f"{type(exc).__name__}: {exc}"[:200]


def create_backup(session: Session) -> BackupResult:
    """Write, verify, and retain one backup. Raises ConflictError (HTTP 409) when
    backups are switched off or the database engine cannot be snapshotted."""
    if not bool(get_setting(session, "backup_enabled", False)):
        raise ConflictError(
            "backups are disabled — enable them in Settings "
            "(a backup writes files outside the database, so it is opt-in)"
        )
    if not is_supported(session):
        raise ConflictError(
            "database backup is SQLite-only; on Postgres use pg_dump or your "
            "platform's managed snapshots (point-in-time recovery)"
        )

    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = _target(directory)

    # VACUUM cannot run inside a transaction. Committing first ends the session's
    # auto-begun read transaction, and running on a dedicated AUTOCOMMIT
    # connection keeps this correct even when the pool hands back the same
    # underlying connection.
    session.commit()
    engine = session.get_bind()
    # The path is server-owned (env ceiling + generated name), never client input;
    # the quote-escape keeps the statement well-formed for an odd directory name.
    literal = str(target).replace("'", "''")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"VACUUM INTO '{literal}'")

    _verify(target)
    offsite, offsite_error = _push_offsite(session, target)

    # One source of truth for the floor/corrupt-value handling (settings_service).
    pruned = _prune(backup_retention(session))

    create_audit_event(
        session,
        event_type="backup",
        actor_type="human",
        entity_type="backup",
        entity_id=target.name,
    )
    session.commit()
    return BackupResult(
        backup=_describe(target),
        pruned=pruned,
        offsite=offsite,
        offsite_error=offsite_error,
    )


# --- restore (D43: CLI only, app stopped — never an HTTP route) ---------------

# Replacing the database file while stale WAL/shared-memory sidecars remain lets
# SQLite replay frames belonging to the *old* database over the restored one.
# That is a real corruption path, so they move aside with it, never left behind.
_SIDECARS = ("-wal", "-shm")


def database_path() -> Path:
    """Filesystem path of the configured SQLite database.

    Read from config rather than an engine because restore runs with the app
    stopped, where there is no engine to ask.
    """
    url = make_url(env.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ConflictError(
            "restore is SQLite-only; on Postgres restore from pg_dump or your "
            "platform's managed snapshot (point-in-time recovery)"
        )
    return Path(url.database)


def resolve_backup(name: str) -> Path:
    """Resolve a backup **by name within the configured directory**.

    Trust boundary: the name must match a pattern we generated. That pattern
    contains no separators or dots-segments, so a caller cannot traverse out of
    the backup directory or aim restore at an arbitrary file on disk.
    """
    if not _NAME_RE.match(name):
        raise ConflictError(f"not a recognized backup name: {name!r}")
    path = backup_dir() / name
    if not path.is_file():
        raise ConflictError(f"backup not found: {name}")
    return path


def verify_backup(name: str) -> Path:
    """Integrity-check an existing backup, leaving it in place.

    Unlike the post-write check, a failure here does **not** delete anything —
    the operator is inspecting, and a suspect file may still be the best copy
    they have.
    """
    path = resolve_backup(name)
    if not _integrity_ok(path):
        raise ConflictError(f"backup {name} FAILED its integrity check")
    return path


def restore_backup(name: str) -> RestoreResult:
    """Replace the live database with a verified backup. **App must be stopped.**

    The order is the substance of D43:

      1. verify the backup *first* — never overwrite good data with a bad copy;
      2. move the live database and its sidecars aside as ``.pre-restore-<stamp>``
         so a mistaken restore is reversible and no stale WAL frame survives;
      3. copy the backup into place and re-check that what landed is intact.
    """
    source = verify_backup(name)
    target = database_path()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    displaced: list[str] = []
    for suffix in ("", *_SIDECARS):
        live = Path(f"{target}{suffix}")
        if live.exists():
            aside = Path(f"{live}.pre-restore-{stamp}")
            live.replace(aside)  # atomic; keeps the previous state recoverable
            displaced.append(aside.name)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if not _integrity_ok(target):
        raise ConflictError(
            "the restored database failed its integrity check — the previous "
            f"state is preserved as {displaced or ['(nothing to displace)']}"
        )
    return RestoreResult(restored_from=name, database=target.name, displaced=displaced)
