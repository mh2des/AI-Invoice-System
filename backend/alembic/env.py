import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect them
from app.db.base import Base
from app.models import Supplier, Product, Invoice, InvoiceItem, ChatSession, ChatMessage  # noqa: F401
from app.core.config import get_settings

target_metadata = Base.metadata

settings = get_settings()

# Build a sync psycopg2 URL from the asyncpg URL for use in Alembic
# (Alembic works better with sync connections; app runtime still uses asyncpg)
def _get_sync_url() -> str:
    url = settings.DATABASE_URL
    # Replace asyncpg driver with psycopg2
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    # Strip ?ssl=require query param — psycopg2 handles SSL via connect_args
    if "?ssl=" in url:
        url = url.split("?ssl=")[0]
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=_get_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using sync psycopg2 engine."""
    connect_args = {}
    if "supabase.com" in settings.DATABASE_URL:
        connect_args = {"sslmode": "require"}

    connectable = create_engine(
        _get_sync_url(),
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

