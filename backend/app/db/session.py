import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Ensure the URL uses the asyncpg driver (user may set plain postgresql:// in env)
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

# Add SSL for remote databases (Supabase/production)
_connect_args = {}
if "supabase.com" in _db_url or "pooler.supabase" in _db_url:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args = {"ssl": _ssl_ctx}

engine = create_async_engine(_db_url, echo=False, connect_args=_connect_args)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Alias for use in background tasks (direct context manager, no DI)
async_session_factory = async_session


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
