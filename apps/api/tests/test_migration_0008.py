"""Migration 0008: agentrun / notificationrule / emaillog tables (Phase 9)."""
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parents[1]

_NEW_TABLES = {"agentrun", "notificationrule", "emaillog"}


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


def test_0008_upgrade_and_downgrade(tmp_path):
    db_path = tmp_path / "m8.db"
    cfg = _config(db_path)

    command.upgrade(cfg, "head")
    assert _NEW_TABLES <= _tables(db_path)

    command.downgrade(cfg, "0007")
    tables = _tables(db_path)
    assert not (_NEW_TABLES & tables)
    assert "apiclient" in tables  # earlier revisions untouched

    command.upgrade(cfg, "head")
    assert _NEW_TABLES <= _tables(db_path)


def test_0008_checks_enforced(tmp_path):
    db_path = tmp_path / "m8c.db"
    cfg = _config(db_path)
    command.upgrade(cfg, "head")

    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "INSERT INTO workspace (id,name,slug,created_at,updated_at) "
            "VALUES ('ws','W','w','2026','2026')"
        )
        con.execute(
            "INSERT INTO project (id,workspace_id,title,slug,status,created_at,updated_at) "
            "VALUES ('pr','ws','P','p','active','2026','2026')"
        )
        con.execute(
            "INSERT INTO agentrun (id,project_id,agent_family,status,started_at,"
            "created_at,updated_at) VALUES ('run_1','pr','claude','started','2026','2026','2026')"
        )
        con.commit()

        for stmt, label in (
            (
                "INSERT INTO agentrun (id,project_id,agent_family,status,started_at,"
                "created_at,updated_at) VALUES ('run_2','pr','skynet','started','2026','2026','2026')",
                "bad family",
            ),
            (
                "INSERT INTO agentrun (id,project_id,agent_family,status,started_at,"
                "created_at,updated_at) VALUES ('run_3','pr','claude','exploded','2026','2026','2026')",
                "bad status",
            ),
            (
                "INSERT INTO notificationrule (id,project_id,channel,trigger_type,enabled,"
                "to_email,threshold_hours,created_at,updated_at) "
                "VALUES ('nrl_1','pr','fax','due_soon',1,'a@b.co',48,'2026','2026')",
                "bad channel",
            ),
            (
                "INSERT INTO notificationrule (id,project_id,channel,trigger_type,enabled,"
                "to_email,threshold_hours,created_at,updated_at) "
                "VALUES ('nrl_2','pr','email','due_soon',1,'a@b.co',0,'2026','2026')",
                "zero threshold",
            ),
            (
                "INSERT INTO emaillog (id,project_id,to_email,subject,status,sent_at,created_at) "
                "VALUES ('eml_1','pr','a@b.co','s','bounced','2026','2026')",
                "bad email status",
            ),
        ):
            try:
                con.execute(stmt)
                con.commit()
                raise AssertionError(f"{label} should have been rejected")
            except sqlite3.IntegrityError:
                con.rollback()
    finally:
        con.close()
