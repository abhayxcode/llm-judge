"""Tests for /v1/labels and /v1/agreement.

ClickHouse is unavailable in unit tests, so judge-vs-human stats come back
None; the route still writes a valid AgreementMetric snapshot.
"""

from __future__ import annotations

from typing import Any

import pytest_asyncio
from fastapi.testclient import TestClient
from judge_api.routes import labels as labels_module
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


@pytest_asyncio.fixture
async def seeded(
    db_app: TestClient,
    session_factory: async_sessionmaker,
    monkeypatch: Any,
) -> dict[str, Any]:
    """Project + metric + 3-record dataset already in place. CH stubbed off
    so agreement recompute is hermetic."""
    monkeypatch.setattr(labels_module, "_safe_ch_client", lambda _r: None)
    async with session_factory() as session:
        await insert_project(session)
    db_app.post("/v1/metrics", json={"project": "demo", "ir": _ir()})
    rec_resp = db_app.post(
        "/v1/datasets",
        json={
            "project": "demo",
            "slug": "seed",
            "name": "Seed",
            "records": [
                {"input": {"x": "alpha"}},
                {"input": {"x": "beta"}},
                {"input": {"x": "gamma"}},
            ],
        },
    )
    assert rec_resp.status_code == 200
    records = db_app.get(
        "/v1/datasets/seed/versions/1/records?project=demo"
    ).json()
    return {"records": records}


async def test_create_label_writes_row_and_agreement(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    rec_id = seeded["records"][0]["id"]
    r = db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "faithfulness",
            "record_id": rec_id,
            "user_email": "a@example.com",
            "score": 4,
            "rationale": "looks faithful",
            "tags": ["clean"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score"] == 4
    assert body["user_email"] == "a@example.com"

    ag = db_app.get(
        "/v1/agreement?project=demo&metric=faithfulness"
    ).json()
    assert ag is not None
    assert ag["n_labels"] == 1
    # Without judge scores in CH, judge-vs-human stats are null.
    assert ag["cohen_kappa"] is None


async def test_label_upsert_overwrites_same_user(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    rec_id = seeded["records"][0]["id"]
    payload = {
        "project": "demo",
        "metric_slug": "faithfulness",
        "record_id": rec_id,
        "user_email": "a@example.com",
        "score": 2,
    }
    db_app.post("/v1/labels", json=payload)
    payload["score"] = 5
    r = db_app.post("/v1/labels", json=payload)
    assert r.status_code == 200
    listing = db_app.get(
        "/v1/labels?project=demo&metric=faithfulness"
    ).json()
    assert len(listing) == 1
    assert listing[0]["score"] == 5


async def test_list_labels_filter_by_user(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    rec_id = seeded["records"][0]["id"]
    db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "faithfulness",
            "record_id": rec_id,
            "user_email": "a@example.com",
            "score": 3,
        },
    )
    db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "faithfulness",
            "record_id": rec_id,
            "user_email": "b@example.com",
            "score": 5,
        },
    )
    only_a = db_app.get(
        "/v1/labels?project=demo&metric=faithfulness&user_email=a@example.com"
    ).json()
    assert len(only_a) == 1
    assert only_a[0]["user_email"] == "a@example.com"


async def test_unknown_record_returns_404(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    r = db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "faithfulness",
            "record_id": "01ZZZZZZZZZZZZZZZZZZZZZZZZ",
            "user_email": "a@example.com",
            "score": 3,
        },
    )
    assert r.status_code == 404


async def test_unknown_metric_returns_404(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    rec_id = seeded["records"][0]["id"]
    r = db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "ghost",
            "record_id": rec_id,
            "user_email": "a@example.com",
            "score": 3,
        },
    )
    assert r.status_code == 404


async def test_agreement_recompute_endpoint(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    rec_id = seeded["records"][0]["id"]
    db_app.post(
        "/v1/labels",
        json={
            "project": "demo",
            "metric_slug": "faithfulness",
            "record_id": rec_id,
            "user_email": "a@example.com",
            "score": 3,
        },
    )
    r = db_app.post(
        "/v1/agreement/recompute",
        json={"project": "demo", "metric": "faithfulness"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_labels"] == 1
    assert body["metric_slug"] == "faithfulness"


async def test_fleiss_emerges_with_three_raters_per_record(
    db_app: TestClient, seeded: dict[str, Any]
) -> None:
    rec_ids = [r["id"] for r in seeded["records"]]
    raters = [("a@example.com", 5), ("b@example.com", 5), ("c@example.com", 4)]
    for rid in rec_ids:
        for email, score in raters:
            db_app.post(
                "/v1/labels",
                json={
                    "project": "demo",
                    "metric_slug": "faithfulness",
                    "record_id": rid,
                    "user_email": email,
                    "score": score,
                },
            )
    ag = db_app.get(
        "/v1/agreement?project=demo&metric=faithfulness"
    ).json()
    # All raters give 4 or 5; only one ordinal split → Fleiss is well-defined.
    assert ag["fleiss_kappa"] is not None
    assert ag["n_labels"] == 9
