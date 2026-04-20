"""Alembic migration environment for an async SQLAlchemy app.

Design:
- DATABASE_URL comes from `app.config.settings` (single source of truth).
- Models are imported from `app.models` so `Base.metadata` is populated
  for `--autogenerate`.
- Online mode uses an async engine; we bridge to Alembic's sync API via
  `connection.run_sync(do_run_migrations)`.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import settings and models. Importing `app.models` is what attaches
# every table to `Base.metadata` for autogenerate to work.
from app.config import settings
from app.database import _normalize_async_url
from app.models import Base  # noqa: F401  (ensures User is registered)

# Alembic Config object.
config = context.config

# Inject DATABASE_URL from settings (normalisée pour asyncpg) so alembic.ini
# stays environment-free. Railway peut fournir `postgres://...` → on
# transforme en `postgresql+asyncpg://...` au runtime.
config.set_main_option("sqlalchemy.url", _normalize_async_url(settings.DATABASE_URL))

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL without a DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
