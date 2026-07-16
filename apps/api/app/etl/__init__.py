"""Application-level database ETL (Phase 10.5).

An offline, one-shot copy of every model table from a source database (typically
local SQLite) into a target (typically hosted Postgres), in foreign-key-safe order
with row-count verification. This is the deliberate SQLite→Postgres path (D23):
`pg_upgrade` and logical replication can't migrate SQLite, so data movement is an
explicit application-level export/import rather than a DB-engine feature.

Off by default and standalone — importing this package changes nothing about the
running app; it's exercised only by ``scripts/migrate_db.py`` and its tests.
"""
from app.etl.migrate import EtlError, copy_all

__all__ = ["EtlError", "copy_all"]
