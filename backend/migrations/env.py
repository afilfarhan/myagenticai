"""
Alembic environment for SentinelChain.

Resolves the database URL from DATABASE__URL or backend/config.yaml and points
target_metadata at the application's SQLAlchemy metadata so autogenerate
produces correct migrations.
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the `app` package importable when running from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.config import reset_config  # noqa: E402

reset_config()

from app.services.database import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Database URL for synchronous Alembic engines."""
    url = os.getenv("DATABASE__URL")
    if not url:
        from app.services.config import get_config

        url = get_config().database.url
    # Alembic runs sync engines; translate the async sqlite driver.
    return url.replace("sqlite+aiosqlite", "sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with an Engine + connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTERs
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
