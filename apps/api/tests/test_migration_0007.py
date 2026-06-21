"""Phase 7C1: migration 0007 — apiclient table + 'api' origin, safe downgrade."""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parents[1]

_APPROVAL_INSERT = (
    "INSERT INTO approvalrequest "
    "(id,workspace_id,project_id,origin,action_type,proposed_patch_json,"
    "patch_checksum,policy_version,risk_level,status,created_at,expires_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
)


def _row(**k):
    return [
        k.get("id", "apr_t"), "ws", "pr", k.get("origin", "local"),
        k.get("action_type", "task.create"), "{}", "c", 1, "low",
        k.get("status", "pending"), "2026", "2027",
    ]


def _config(db_path: Path) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def _indexes(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        con.close()


def test_0007_creates_apiclient_and_preserves_approval_schema(tmp_path):
    db = tmp_path / "m7.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")

    tables = _tables(db)
    assert "apiclient" in tables
    idx = _indexes(db)
    assert "ix_apiclient_key_id" in idx
    # Existing approval idempotency + indexes survive the batch CHECK widening.
    assert "uq_approval_active_idem" in idx
    assert {"ix_approval_status", "ix_approval_origin", "ix_approval_expires_at"} <= idx


def test_0007_origin_check_accepts_api_rejects_unknown(tmp_path):
    db = tmp_path / "m7c.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    try:
        con.execute(_APPROVAL_INSERT, _row(id="apr_api", origin="api"))
        con.commit()  # 'api' accepted
        con.execute(_APPROVAL_INSERT, _row(id="apr_mcp", origin="mcp"))
        con.commit()  # 'mcp' still accepted
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_APPROVAL_INSERT, _row(id="apr_bad", origin="zzz"))
            con.commit()
        con.rollback()
        # A non-origin CHECK (status) is still enforced too.
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_APPROVAL_INSERT, _row(id="apr_st", status="weird"))
            con.commit()
        con.rollback()
    finally:
        con.close()


def test_0007_clean_roundtrip(tmp_path):
    db = tmp_path / "m7r.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    assert "apiclient" in _tables(db)
    command.downgrade(cfg, "0006")
    assert "apiclient" not in _tables(db)
    # After downgrade the origin CHECK is narrow again: 'api' must be rejected.
    con = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_APPROVAL_INSERT, _row(id="apr_api2", origin="api"))
            con.commit()
        con.rollback()
    finally:
        con.close()
    command.upgrade(cfg, "head")
    assert "apiclient" in _tables(db)


def test_0007_downgrade_refuses_when_api_origin_rows_exist(tmp_path):
    db = tmp_path / "m7safe.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    con.execute(_APPROVAL_INSERT, _row(id="apr_keep", origin="api"))
    con.commit()
    con.close()

    with pytest.raises(Exception):  # RuntimeError from the migration downgrade
        command.downgrade(cfg, "0006")

    # Data is NOT deleted: the table and the api row are still there.
    assert "apiclient" in _tables(db)
    con = sqlite3.connect(db)
    try:
        n = con.execute("SELECT COUNT(*) FROM approvalrequest WHERE origin='api'").fetchone()[0]
        assert n == 1
    finally:
        con.close()


def test_0007_downgrade_refuses_when_apiclient_rows_exist(tmp_path):
    db = tmp_path / "m7safe2.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO apiclient (id,workspace_id,key_id,secret_hash,label,can_read,"
        "can_propose,project_ids_json,enabled,created_at,expires_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ["apc_1", "ws", "kid", "$argon2id$x", "l", 1, 0, "[]", 1, "2026", "2027"],
    )
    con.commit()
    con.close()

    with pytest.raises(Exception):
        command.downgrade(cfg, "0006")

    assert "apiclient" in _tables(db)
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM apiclient").fetchone()[0] == 1
    finally:
        con.close()
