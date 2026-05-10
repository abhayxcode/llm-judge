"""Tests for the GET /v1/traces endpoints.

We avoid hitting a live ClickHouse by mocking `_client` to return a fake
client whose `.query(...)` returns canned rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from judge_api.config import Settings
from judge_api.main import create_app
from judge_api.routes import traces as traces_module


class FakeQueryResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def named_results(self) -> list[dict[str, Any]]:
        return self._rows


class FakeCHClient:
    def __init__(self, rows_by_query: list[list[dict[str, Any]]]) -> None:
        self._batches = list(rows_by_query)

    def query(self, _sql: str, parameters: dict[str, Any] | None = None) -> FakeQueryResult:
        return FakeQueryResult(self._batches.pop(0))


def _summary_row() -> dict[str, Any]:
    return {
        "trace_id": "01TRACE",
        "org_id": "default",
        "project_id": "demo",
        "name": "rag_chain",
        "first_seen": datetime(2026, 5, 10, 0, 0, 0),
        "last_seen": datetime(2026, 5, 10, 0, 0, 1),
        "duration_ms": 1000,
        "span_count": 2,
        "root_span_count": 1,
        "status": "ok",
        "error": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def _span_row(span_id: str, parent: str | None) -> dict[str, Any]:
    return {
        "span_id": span_id,
        "parent_span_id": parent,
        "name": "step",
        "start_ts": datetime(2026, 5, 10, 0, 0, 0),
        "end_ts": datetime(2026, 5, 10, 0, 0, 1),
        "duration_ms": 1000,
        "status": "ok",
        "error": None,
        "attributes": {"k": "v"},
        "gen_ai_system": "",
        "gen_ai_model": "",
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _client_with_batches(
    monkeypatch: pytest.MonkeyPatch, batches: list[list[dict[str, Any]]]
) -> TestClient:
    app = create_app(Settings(env="test"))
    fake = FakeCHClient(rows_by_query=batches)
    monkeypatch.setattr(traces_module, "_client", lambda _request: fake)
    return TestClient(app)


def test_list_traces(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_batches(monkeypatch, [[_summary_row()]])
    resp = client.get("/v1/traces?project=demo&limit=10")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["trace_id"] == "01TRACE"
    assert body[0]["span_count"] == 2


def test_get_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_batches(
        monkeypatch,
        [
            [_summary_row()],  # summary lookup
            [_span_row("01ROOT", None), _span_row("01CHILD", "01ROOT")],  # spans
        ],
    )
    resp = client.get("/v1/traces/01TRACE?project=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["trace_id"] == "01TRACE"
    span_ids = [s["span_id"] for s in body["spans"]]
    assert span_ids == ["01ROOT", "01CHILD"]
    assert body["spans"][1]["parent_span_id"] == "01ROOT"


def test_get_trace_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_batches(monkeypatch, [[]])
    resp = client.get("/v1/traces/missing?project=demo")
    assert resp.status_code == 404
