"""Tests for the M2 runs endpoints. Redis is faked in-process."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from judge_api.routes import runs as runs_module
from sqlalchemy.ext.asyncio import async_sessionmaker

from .conftest import insert_project


class FakeRedisPipeline:
    def __init__(self, owner: FakeRedis) -> None:
        self.owner = owner

    def xadd(self, stream: str, fields: dict[Any, Any], **_: Any) -> None:
        self.owner.entries.append((stream, fields))

    async def execute(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[Any, Any]]] = []

    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()

    async def _redis_stub(_request: Any) -> FakeRedis:
        return fake

    monkeypatch.setattr(runs_module, "_redis", _redis_stub)
    return fake


def _ir(prompt: str = "rate {{x}}") -> dict[str, Any]:
    return {
        "id": "faithfulness",
        "name": "Faithfulness",
        "scoring_type": "pointwise",
        "scale": {"min": 1, "max": 5},
        "prompt_template": prompt,
        "judge_config": {"model": "anthropic/claude-sonnet-4-6"},
    }


async def test_create_run_enqueues_one_per_record(
    db_app: TestClient,
    session_factory: async_sessionmaker,
    fake_redis: FakeRedis,
) -> None:
    async with session_factory() as session:
        await insert_project(session)

    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir()})
    db_app.post(
        "/v1/datasets",
        json={
            "project": "demo",
            "slug": "seed",
            "name": "Seed",
            "records": [{"input": {"x": "a"}}, {"input": {"x": "b"}}, {"input": {"x": "c"}}],
        },
    )

    resp = db_app.post(
        "/v1/runs",
        json={
            "project": "demo",
            "name": "test run",
            "metric_slug": "faithfulness",
            "dataset_slug": "seed",
        },
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["status"] == "queued"
    assert run["record_count"] == 3
    assert len(fake_redis.entries) == 3
    assert fake_redis.entries[0][0] == "judge:evals"


async def test_list_and_get_run(
    db_app: TestClient,
    session_factory: async_sessionmaker,
    fake_redis: FakeRedis,
) -> None:
    async with session_factory() as session:
        await insert_project(session)

    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir()})
    db_app.post(
        "/v1/datasets",
        json={
            "project": "demo",
            "slug": "seed",
            "name": "Seed",
            "records": [{"input": {"x": "a"}}],
        },
    )
    create = db_app.post(
        "/v1/runs",
        json={
            "project": "demo",
            "name": "r",
            "metric_slug": "faithfulness",
            "dataset_slug": "seed",
        },
    ).json()

    listing = db_app.get("/v1/runs?project=demo").json()
    assert len(listing) == 1

    detail = db_app.get(f"/v1/runs/{create['id']}").json()
    assert detail["id"] == create["id"]
    assert detail["record_count"] == 1


async def test_create_run_unknown_metric(
    db_app: TestClient,
    session_factory: async_sessionmaker,
    fake_redis: FakeRedis,
) -> None:
    async with session_factory() as session:
        await insert_project(session)
    r = db_app.post(
        "/v1/runs",
        json={
            "project": "demo",
            "name": "r",
            "metric_slug": "ghost",
            "dataset_slug": "x",
        },
    )
    assert r.status_code == 404
