"""FK-ordered full-table copy between two databases (Phase 10.5).

Uses the shared SQLModel table metadata for both ends, so column types are
interpreted consistently across dialects (e.g. SQLite 0/1 → Postgres boolean).
Tables are copied in ``metadata.sorted_tables`` order so a child's foreign keys
always land after their parents. The whole target write is one transaction — on
any error nothing is committed.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, func, select
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers every table in SQLModel.metadata


class EtlError(Exception):
    """A migration precondition or verification failed."""


def _count(conn, table) -> int:
    return conn.execute(select(func.count()).select_from(table)).scalar() or 0


def copy_all(
    source_url: str,
    target_url: str,
    *,
    allow_nonempty_target: bool = False,
    batch_size: int = 500,
) -> dict[str, int]:
    """Copy every model table from ``source_url`` to ``target_url``.

    The target schema must already exist (run ``alembic upgrade head`` against it
    first; ``scripts/migrate_db.py`` does this). Refuses to run if any target table
    already holds rows unless ``allow_nonempty_target`` is set, so a re-run can't
    silently duplicate data. Returns ``{table_name: rows_copied}``. Raises
    ``EtlError`` if a post-copy row-count check doesn't match.
    """
    if source_url == target_url:
        raise EtlError("source and target must differ")

    source = create_engine(source_url)
    target = create_engine(target_url)
    tables = list(SQLModel.metadata.sorted_tables)
    report: dict[str, int] = {}

    with source.connect() as src, target.begin() as tgt:
        # Guardrail: never write into a non-empty target unless told to.
        if not allow_nonempty_target:
            for table in tables:
                existing = _count(tgt, table)
                if existing:
                    raise EtlError(
                        f"target table {table.name!r} already has {existing} row(s); "
                        "refusing to copy into a non-empty target"
                    )
        # Copy parents-before-children.
        for table in tables:
            rows = [dict(m) for m in src.execute(table.select()).mappings().all()]
            for start in range(0, len(rows), batch_size):
                chunk = rows[start : start + batch_size]
                if chunk:
                    tgt.execute(table.insert(), chunk)
            report[table.name] = len(rows)

    # Verify counts match end-to-end.
    with source.connect() as src, target.connect() as tgt:
        for table in tables:
            s, t = _count(src, table), _count(tgt, table)
            if s != t:
                raise EtlError(
                    f"row-count mismatch for {table.name!r}: source={s} target={t}"
                )

    return report
