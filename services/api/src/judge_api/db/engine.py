"""Database engines + session factories.

Async SQLAlchemy for the FastAPI app and workers. Sync engine exposed for
alembic via :func:`sync_engine_url`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from judge_api.config import Settings, get_settings


def async_engine_url(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return f"postgresql+asyncpg://{s.pg_user}:{s.pg_password}@{s.pg_host}:{s.pg_port}/{s.pg_db}"


def sync_engine_url(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    # asyncpg is async-only; alembic uses psycopg via the default dialect.
    return f"postgresql+psycopg://{s.pg_user}:{s.pg_password}@{s.pg_host}:{s.pg_port}/{s.pg_db}"


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(async_engine_url(), pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
