"""Tests for /v1/queue active-learning endpoints.

CH is unavailable in unit tests, so the low_confidence strategy contributes
nothing — we exercise drift_outlier (length-based) and the queue lifecycle
(claim, skip, refresh wipes-and-rebuilds).
"""

from __future__ import annotations

from typing import Any

import pytest_asyncio
from fastapi.testclient import TestClient
from judge_api.routes import labels as labels_module
from judge_api.routes import queue as queue_module
from judge_api.routes import runs as runs_module
from sqlalchemy.ext.asyncio import async_sessionmaker

from .conftest import insert_project


def _ir(slug: str = "faithfulness") -> dict[str, Any]:
    return {
        "id": slug,
        "name": slug.title(),
        "scoring_type": "pointwise",
        "scale": {"min": 1, "max": 5},
        "prompt_template": "rate {{x}}",
        "judge_config": {"model": "anthropic/claude-sonnet-4-6"},
    }


class _FakeRedis:
    def pipeline(self) -> _FakePipeline:
        return _FakePipeline()


class _FakePipeline:
    def xadd(self, *_a: Any, **_k: Any) -> None: ...
    async def execute(self) -> None: ...


@pytest_asyncio.fixture
async def seeded(
    db_app: TestClient,
    session_factory: async_sessionmaker,
    monkeypatch: Any,
) -> dict[str, Any]:
    async def _redis_stub(_request: Any) -> _FakeRedis:
        return _FakeRedis()

    monkeypatch.setattr(runs_module, "_redis", _redis_stub)
    monkeypatch.setattr(queue_module, "_safe_ch_client", lambda _r: None)
    monkeypatch.setattr(labels_module, "_safe_ch_client", lambda _r: None)

    async with session_factory() as session:
        await insert_project(session)

    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir()})
    # 5 records of varying lengths so drift_outlier ranks the long one high.
    db_app.post(
        "/v1/datasets",
        json={
            "project": "demo",
            "slug": "seed",
            "name": "Seed",
            "records": [
                {"input": {"x": "a"}},
                {"input": {"x": "ab"}},
                {"input": {"x": "abc"}},
                {"input": {"x": "abcd"}},
                {"input": {"x": "x" * 200}},  # outlier
            ],
        },
    )
    db_app.post(
        "/v1/runs",
        json={
            "project": "demo",
            "name": "test",
            "metric_slug": "faithfulness",
            "dataset_slug": "seed",
        },
    )
    return {}


async def test_refresh_inserts_drift_outlier_at_top(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    r = db_app.post(
        "/v1/queue/refresh",
        json={"project": "demo", "metric": "faithfulness", "queue_size": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] >= 1
    assert "drift_outlier" in body["strategies_used"]

    listing = db_app.get(
        "/v1/queue?project=demo&metric=faithfulness"
    ).json()
    assert len(listing) >= 1
    # Highest-priority should be the long outlier.
    top = listing[0]
    assert top["strategy"] == "drift_outlier"
    assert top["priority"] > 0


async def test_refresh_wipes_unclaimed_rows(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    db_app.post(
        "/v1/queue/refresh",
        json={"project": "demo", "metric": "faithfulness", "queue_size": 10},
    )
    first_count = len(
        db_app.get("/v1/queue?project=demo&metric=faithfulness").json()
    )
    db_app.post(
        "/v1/queue/refresh",
        json={"project": "demo", "metric": "faithfulness", "queue_size": 10},
    )
    second_count = len(
        db_app.get("/v1/queue?project=demo&metric=faithfulness").json()
    )
    # Same dataset → same candidates → same row count.
    assert first_count == second_count


async def test_claim_then_skip_lifecycle(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    db_app.post(
        "/v1/queue/refresh",
        json={"project": "demo", "metric": "faithfulness", "queue_size": 10},
    )
    items = db_app.get(
        "/v1/queue?project=demo&metric=faithfulness"
    ).json()
    assert items
    qid = items[0]["id"]

    r = db_app.post(
        f"/v1/queue/{qid}/claim",
        json={"user_email": "anna@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["claimed_by"] is not None
    assert body["claimed_at"] is not None

    # Re-claim by same user is a no-op (allowed).
    r2 = db_app.post(
        f"/v1/queue/{qid}/claim",
        json={"user_email": "anna@example.com"},
    )
    assert r2.status_code == 200

    # Different user gets 409.
    r3 = db_app.post(
        f"/v1/queue/{qid}/claim",
        json={"user_email": "bob@example.com"},
    )
    assert r3.status_code == 409

    skip = db_app.post(
        f"/v1/queue/{qid}/skip",
        json={"reason": "duplicate"},
    )
    assert skip.status_code == 200
    assert skip.json()["completed_at"] is not None


async def test_label_marks_queue_complete(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    db_app.post(
        "/v1/queue/refresh",
        json={"project": "demo", "metric": "faithfulness", "queue_size": 10},
    )
    items = db_app.get("/v1/queue?project=demo&metric=faithfulness").json()
    target = items[0]
    rec_id = target["record_id"]

    db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "faithfulness",
            "record_id": rec_id,
            "user_email": "alice@example.com",
            "score": 4,
        },
    )

    pending = db_app.get(
        "/v1/queue?project=demo&metric=faithfulness&pending_only=true"
    ).json()
    assert all(item["record_id"] != rec_id for item in pending)


async def test_unknown_metric_404(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    r = db_app.post(
        "/v1/queue/refresh",
        json={"project": "demo", "metric": "ghost", "queue_size": 5},
    )
    assert r.status_code == 404
