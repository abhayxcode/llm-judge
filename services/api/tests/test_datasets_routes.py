"""Tests for the M2 dataset endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from .conftest import insert_project


async def test_create_and_list_datasets(
    db_app: TestClient, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as session:
        await insert_project(session)

    body = {
        "project": "demo",
        "slug": "seed",
        "name": "Seed",
        "records": [
            {"input": {"q": "hi"}, "expected_output": "hello", "context": None},
            {"input": {"q": "bye"}, "expected_output": "goodbye", "context": {"k": "v"}},
        ],
    }
    r = db_app.post("/v1/datasets", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"] == 1
    assert out["record_count"] == 2

    listing = db_app.get("/v1/datasets?project=demo").json()
    assert len(listing) == 1
    assert listing[0]["slug"] == "seed"
    assert listing[0]["record_count"] == 2

    recs = db_app.get("/v1/datasets/seed/versions/1/records?project=demo").json()
    assert [r["row_index"] for r in recs] == [0, 1]
    assert recs[1]["context"] == {"k": "v"}


async def test_create_empty_dataset_rejected(
    db_app: TestClient, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as session:
        await insert_project(session)
    r = db_app.post(
        "/v1/datasets", json={"project": "demo", "slug": "x", "name": "x", "records": []}
    )
    assert r.status_code == 400


async def test_dataset_versions_increment(
    db_app: TestClient, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as session:
        await insert_project(session)
    payload = {
        "project": "demo",
        "slug": "seed",
        "name": "Seed",
        "records": [{"input": {"q": "hi"}}],
    }
    v1 = db_app.post("/v1/datasets", json=payload).json()
    v2 = db_app.post("/v1/datasets", json=payload).json()
    assert v1["version"] == 1
    assert v2["version"] == 2
