"""CLI: migrate an Approvo database from one URL to another (Phase 10.5).

The deliberate SQLite→Postgres path (D23). By default it migrates the target
schema to head, then copies every table in FK-safe order with verification.

    cd apps/api && python scripts/migrate_db.py \\
        --source sqlite:///./agentboard.db \\
        --target postgresql+psycopg2://user:pass@host:5432/approvo

Safe by construction: refuses a non-empty target unless --allow-nonempty, and the
target write is one transaction. Run against a fresh target you control.
"""
import argparse
import sys

from alembic import command
from alembic.config import Config

from app.etl import EtlError, copy_all


def _upgrade_target(target_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    # Set the URL programmatically; env.py leaves a programmatic URL in place
    # (it only overrides from AGENTBOARD_DATABASE_URL/DATABASE_URL env vars).
    cfg.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy an Approvo DB source→target.")
    ap.add_argument("--source", required=True, help="source SQLAlchemy URL")
    ap.add_argument("--target", required=True, help="target SQLAlchemy URL")
    ap.add_argument(
        "--no-migrate",
        action="store_true",
        help="skip 'alembic upgrade head' on the target (assume it's at head)",
    )
    ap.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="permit copying into a target that already has rows (dangerous)",
    )
    args = ap.parse_args()

    if not args.no_migrate:
        print(f"Migrating target schema to head: {args.target}")
        _upgrade_target(args.target)

    try:
        report = copy_all(
            args.source, args.target, allow_nonempty_target=args.allow_nonempty
        )
    except EtlError as exc:
        print(f"ETL failed: {exc}", file=sys.stderr)
        return 1

    total = sum(report.values())
    print(f"Copied {total} row(s) across {len(report)} tables:")
    for name, n in report.items():
        if n:
            print(f"  {name}: {n}")
    print("Verification passed (source and target row counts match).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
