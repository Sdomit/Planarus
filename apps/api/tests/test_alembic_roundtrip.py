"""Alembic upgrade head → downgrade base round-trip on a temp SQLite file."""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_cfg(tmp_path):
    db_path = tmp_path / "roundtrip.db"
    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg, db_path


def test_alembic_upgrade_downgrade(alembic_cfg):
    cfg, db_path = alembic_cfg

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    assert "workspace" in tables
    assert "project" in tables
    assert "auditevent" in tables
    engine.dispose()

    command.downgrade(cfg, "base")

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    assert "workspace" not in tables
    assert "project" not in tables
    assert "auditevent" not in tables
    engine.dispose()
