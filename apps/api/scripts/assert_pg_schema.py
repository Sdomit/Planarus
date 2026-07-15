"""Assert the Postgres schema produced by `alembic upgrade head` (P10.0).

Guards the three dialect-portability fixes so they cannot silently regress:

1. The active-only idempotency index keeps its partial WHERE predicate on
   Postgres (a bare ``sqlite_where`` is silently ignored there, which would
   widen it to a full unique constraint and break idempotency scoping).
2. ``apiclient.enabled`` has a proper boolean server default.
3. ``ck_apiclient_at_least_one_perm`` actually rejects a both-false row.

Run with AGENTBOARD_DATABASE_URL (or DATABASE_URL) pointing at a migrated,
disposable Postgres database. Exits non-zero on the first failed assertion.
The inserted probe rows are rolled back.
"""
import os
import sys

from sqlalchemy import create_engine, inspect, text

REQUIRED_TABLES = {
    "workspace",
    "project",
    "auditevent",
    "contextfile",
    "phase",
    "stage",
    "task",
    "decision",
    "risk",
    "blocker",
    "doc",
    "approvalrequest",
    "apiclient",
    "agentrun",
    "notificationrule",
    "emaillog",
    "milestone",
    "checklistitem",
    "comment",
    "link",
}


def main() -> int:
    url = os.environ.get("AGENTBOARD_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("set AGENTBOARD_DATABASE_URL (or DATABASE_URL) to a migrated Postgres DB")
        return 2
    engine = create_engine(url)

    missing = REQUIRED_TABLES - set(inspect(engine).get_table_names())
    assert not missing, f"missing tables after upgrade head: {sorted(missing)}"

    with engine.connect() as conn:
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes"
                " WHERE indexname = 'uq_approval_active_idem'"
            )
        ).scalar()
        assert indexdef and "WHERE" in indexdef and "pending" in indexdef, (
            f"active-idempotency index lost its partial predicate: {indexdef!r}"
        )

        enabled_default = conn.execute(
            text(
                "SELECT column_default FROM information_schema.columns"
                " WHERE table_name = 'apiclient' AND column_name = 'enabled'"
            )
        ).scalar()
        assert enabled_default == "true", (
            f"apiclient.enabled server default is {enabled_default!r}, expected 'true'"
        )

        conn.execute(
            text(
                "INSERT INTO workspace (id, name, slug, created_at, updated_at)"
                " VALUES ('_pgassert_w', 'w', '_pgassert_w', 't', 't')"
            )
        )
        try:
            conn.execute(
                text(
                    "INSERT INTO apiclient (id, workspace_id, key_id, secret_hash,"
                    " label, can_read, can_propose, project_ids_json, created_at,"
                    " expires_at) VALUES ('_pgassert_a', '_pgassert_w', 'k', 'h',"
                    " 'l', false, false, '[]', 't', 't')"
                )
            )
        except Exception as exc:  # expected: CHECK violation
            assert "ck_apiclient_at_least_one_perm" in str(exc), exc
        else:
            raise AssertionError(
                "ck_apiclient_at_least_one_perm accepted a both-false row"
            )
        finally:
            conn.rollback()

    print("Postgres schema assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
