import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parents[1]


def _config(db_path: Path) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()


def test_upgrade_then_downgrade(tmp_path):
    db_path = tmp_path / "migrations.db"
    cfg = _config(db_path)

    command.upgrade(cfg, "head")
    tables = _tables(db_path)
    assert {"workspace", "project", "auditevent", "contextfile"} <= tables
    assert {"phase", "stage", "task", "decision", "risk", "blocker"} <= tables
    assert "doc" in tables
    assert "approvalrequest" in tables

    command.downgrade(cfg, "base")
    tables = _tables(db_path)
    assert "approvalrequest" not in tables
    assert "doc" not in tables
    assert "contextfile" not in tables
    assert "project" not in tables
    assert "workspace" not in tables


def test_downgrade_one_revision_drops_only_approval(tmp_path):
    """0005 -> 0004 removes approvalrequest but keeps every earlier table."""
    db_path = tmp_path / "migrations_step.db"
    cfg = _config(db_path)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004")
    tables = _tables(db_path)
    assert "approvalrequest" not in tables
    assert "doc" in tables
    assert {"task", "decision"} <= tables

    command.upgrade(cfg, "head")
    assert "approvalrequest" in _tables(db_path)


def _indexes(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='approvalrequest'"
            )
        }
    finally:
        con.close()


def test_0006_swaps_idempotency_index(tmp_path):
    """0006 replaces the global unique idempotency index with the active partial one."""
    db_path = tmp_path / "m6.db"
    cfg = _config(db_path)

    command.upgrade(cfg, "head")
    idx = _indexes(db_path)
    assert "uq_approval_active_idem" in idx
    assert "uq_approval_idempotency_key" not in idx

    command.downgrade(cfg, "0005")
    idx = _indexes(db_path)
    assert "uq_approval_active_idem" not in idx
    assert "uq_approval_idempotency_key" in idx

    command.upgrade(cfg, "head")
    assert "uq_approval_active_idem" in _indexes(db_path)


def test_0006_origin_check_allows_mcp(tmp_path):
    """After 0006 the origin CHECK accepts 'mcp' and rejects unknown values;
    other CHECKs (status) still hold."""
    db_path = tmp_path / "m6c.db"
    cfg = _config(db_path)
    command.upgrade(cfg, "head")

    con = sqlite3.connect(db_path)
    base = (
        "INSERT INTO approvalrequest "
        "(id,workspace_id,project_id,origin,action_type,proposed_patch_json,"
        "patch_checksum,policy_version,risk_level,status,created_at,expires_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    row = lambda **k: [
        k.get("id", "apr_t"), "ws", "pr", k.get("origin", "local"),
        k.get("action_type", "task.create"), "{}", "c", 1, "low",
        k.get("status", "pending"), "2026", "2027",
    ]
    try:
        con.execute(base, row(id="apr_mcp", origin="mcp"))
        con.commit()  # mcp accepted
        for kw, label in (
            (dict(id="apr_bad", origin="zzz"), "bad origin"),
            (dict(id="apr_st", status="weird"), "bad status"),
        ):
            try:
                con.execute(base, row(**kw))
                con.commit()
                raise AssertionError(f"{label} should have been rejected")
            except sqlite3.IntegrityError:
                con.rollback()
    finally:
        con.close()
