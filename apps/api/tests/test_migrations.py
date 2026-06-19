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

    command.downgrade(cfg, "base")
    tables = _tables(db_path)
    assert "contextfile" not in tables
    assert "project" not in tables
    assert "workspace" not in tables
