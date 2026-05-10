"""Shared test fixtures.

For DB-backed route tests we swap the production async engine for an
in-memory SQLite engine and create the schema by hand. This keeps unit
tests hermetic — alembic + Postgres is exercised separately in
integration tests once we wire them up.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from judge_api.config import Settings
from judge_api.db import engine as engine_mod
from judge_api.db.models import Base
from judge_api.main import create_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def db_app(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> TestClient:
    """FastAPI TestClient with the DB session factory swapped to SQLite."""
    monkeypatch.setattr(engine_mod, "get_session_factory", lambda: session_factory)
    app = create_app(Settings(env="test"))
    return TestClient(app)


async def insert_project(
    session: AsyncSession, *, slug: str = "demo", project_id: str = "01PROJECT" + "X" * 16
) -> str:
    """Helper: insert an org + project, return project_id."""
    from judge_api.db.models import Org, Project

    pid = project_id[:26]
    session.add(Org(id="01ORG" + "X" * 21, slug="default", name="Default"))
    session.add(
        Project(id=pid, org_id="01ORG" + "X" * 21, slug=slug, name=slug, settings={})
    )
    await session.commit()
    return pid


def _coerce(o: Any) -> Any:
    return o
