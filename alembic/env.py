"""
Alembic environment for Daily Scholar.

Resolution order for the database URL:
  1. config.attributes['sqlalchemy.url']  (set programmatically by callers)
  2. DATABASE_URL environment variable
  3. fallback: sqlite:///./data/daily_scholar.db (matches Settings default)

target_metadata is wired to backend.database.Base so `alembic revision
--autogenerate` picks up model changes. We import Base directly (not via
backend.config) so migrations do not require ANTHROPIC_API_KEY or other
runtime secrets to be present.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# put project root on sys.path so `from backend.database import Base` works
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import Base  # noqa: E402

# this is the Alembic Config object, providing access to values within alembic.ini
config = context.config

# set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _normalize_postgres_url(url: str) -> str:
    """
    Mirror of backend.database.get_database_url's normalization.

    Hosts like Railway / Heroku inject `postgres://...` URLs; SQLAlchemy
    interprets that as the legacy psycopg2 dialect, but we install psycopg
    v3. This shim rewrites the prefix so alembic and the app talk to the
    same driver.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _resolve_database_url() -> str:
    # priority 1: explicit override set by a caller via attributes (tests)
    url = config.attributes.get("sqlalchemy.url") if config.attributes else None
    # priority 2: programmatic caller via set_main_option (what backend/database.py uses)
    if not url:
        url = config.get_main_option("sqlalchemy.url")
    # priority 3: environment variable
    if not url:
        url = os.environ.get("DATABASE_URL")
    # priority 4: default matches backend.config.Settings.database_url
    if not url:
        url = "sqlite:///./data/daily_scholar.db"
    return _normalize_postgres_url(url)


def run_migrations_offline() -> None:
    """Generate SQL without connecting (alembic upgrade --sql > file.sql)."""
    context.configure(
        url=_resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,  # safer ALTER TABLE on SQLite
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    ini_section = config.get_section(config.config_ini_section) or {}
    ini_section["sqlalchemy.url"] = _resolve_database_url()

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
