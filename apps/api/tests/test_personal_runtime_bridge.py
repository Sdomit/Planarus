"""The personal SQLite schema can join the public migration line safely."""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parents[1]


def test_bridge_adds_skipped_public_features(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PLANARUS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = tmp_path / "personal-bridge.db"
    url = f"sqlite:///{db.as_posix()}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE project (id VARCHAR PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO project (id) VALUES ('proj_existing')"))

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.stamp(cfg, "0040")
    command.upgrade(cfg, "0041")

    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        assert "mcp_activity" in inspector.get_table_names()
        assert {"ix_mcp_activity_project_id", "ix_mcp_activity_last_seen"} <= {
            index["name"] for index in inspector.get_indexes("mcp_activity")
        }
        assert "mode" in {column["name"] for column in inspector.get_columns("project")}
        assert conn.execute(sa.text("SELECT mode FROM project")).scalar_one() == "agentic"
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0041"
