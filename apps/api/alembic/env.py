import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import all models so they register in SQLModel.metadata
import app.models  # noqa: F401

from app.core.config import settings

config = context.config

# P10.0: apply the app settings' DB URL only when it was explicitly set via
# environment (PLANARUS_DATABASE_URL / DATABASE_URL). Detection must use the
# environment, not the Config: set_main_option writes into the same parser the
# ini loads into, so a URL set programmatically (the migration tests set one per
# tmp DB) is indistinguishable from the ini value — an unconditional override
# would stomp it. With no env override, whatever the Config already holds (the
# ini default, or a test's URL) stays authoritative. '%' is escaped because
# set_main_option values pass through configparser interpolation.
if os.environ.get("PLANARUS_DATABASE_URL") or os.environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
