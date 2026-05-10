"""Tests for the M2 metric registration / lookup endpoints."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from .conftest import insert_project


def _ir(prompt: str = "rate {{x}}") -> dict[str, Any]:
    return {
        "id": "faithfulness",
        "name": "Faithfulness",
        "description": "",
        "scoring_type": "pointwise",
        "scale": {"min": 1, "max": 5},
        "prompt_template": prompt,
        "judge_config": {"model": "anthropic/claude-sonnet-4-6", "temperature": 0.0},
        "length_control": {"mode": "off"},
    }


async def test_register_metric_idempotent(
    db_app: TestClient, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as session:
        await insert_project(session, slug="demo")

    r1 = db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir()})
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["metric_slug"] == "faithfulness"
    assert body1["version"] == 1

    # Same content → same version (idempotent).
    r2 = db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir()})
    assert r2.status_code == 200
    assert r2.json()["version"] == 1
    assert r2.json()["hash"] == body1["hash"]


async def test_register_metric_bumps_version_on_change(
    db_app: TestClient, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as session:
        await insert_project(session)

    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir("a")})
    r2 = db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir("b")})
    assert r2.status_code == 200
    assert r2.json()["version"] == 2


async def test_list_and_get_metric_version(
    db_app: TestClient, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as session:
        await insert_project(session)

    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir("a")})
    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir("b")})

    listing = db_app.get("/v1/metrics?project=demo").json()
    assert len(listing) == 1
    assert listing[0]["latest_version"] == 2

    v1 = db_app.get("/v1/metrics/faithfulness/versions/1?project=demo").json()
    v2 = db_app.get("/v1/metrics/faithfulness/versions/2?project=demo").json()
    assert v1["ir"]["prompt_template"] == "a"
    assert v2["ir"]["prompt_template"] == "b"


async def test_register_metric_unknown_project(db_app: TestClient) -> None:
    r = db_app.post("/v1/metrics", json={"project": "ghost", "ir": _ir()})
    assert r.status_code == 404
