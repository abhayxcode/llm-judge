"""Unit tests for ClickHouseWriter.

We avoid hitting a live ClickHouse by patching `clickhouse_connect.get_client`
with a fake recorder. Integration tests against a real CH live in M1's
end-to-end smoke test (run via docker-compose).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from judge_workers.ch_writer import ClickHouseWriter
from judge_workers.config import Settings


class FakeCHClient:
    def __init__(self) -> None:
        self.inserted: list[tuple[str, list[list[Any]], list[str]]] = []
        self.closed = False

    def insert(self, table: str, rows: list[list[Any]], column_names: list[str]) -> None:
        self.inserted.append((table, rows, column_names))

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def writer() -> tuple[ClickHouseWriter, FakeCHClient]:
    fake = FakeCHClient()
    with patch("judge_workers.ch_writer.clickhouse_connect.get_client", return_value=fake):
        w = ClickHouseWriter(Settings(env="test"))
    return w, fake


def test_writes_each_span(writer: tuple[ClickHouseWriter, FakeCHClient]) -> None:
    w, fake = writer
    payload = {
        "trace_id": "01TRACE",
        "name": "rag_chain",
        "spans": [
            {
                "span_id": "01SPAN1",
                "parent_id": None,
                "name": "rag_chain",
                "start_ms": 1700000000000,
                "end_ms": 1700000000500,
                "status": "ok",
                "error": None,
                "attributes": {"user": "abhay", "gen_ai.model": "claude-sonnet-4-6"},
            },
            {
                "span_id": "01SPAN2",
                "parent_id": "01SPAN1",
                "name": "retrieve",
                "start_ms": 1700000000100,
                "end_ms": 1700000000200,
                "status": "ok",
                "error": None,
                "attributes": {"k": 5, "gen_ai.usage.input_tokens": 12},
            },
        ],
    }
    inserted = w.write_trace(org_id="default", project_id="demo", payload=payload)
    assert inserted == 2
    assert len(fake.inserted) == 1
    table, rows, cols = fake.inserted[0]
    assert table == "spans"
    assert "trace_id" in cols
    # First row corresponds to root span; parent_id is None
    assert rows[0][cols.index("trace_id")] == "01TRACE"
    assert rows[0][cols.index("parent_span_id")] is None
    assert rows[1][cols.index("parent_span_id")] == "01SPAN1"
    # gen_ai.* extracted to top-level columns
    assert rows[0][cols.index("gen_ai_model")] == "claude-sonnet-4-6"
    assert rows[1][cols.index("input_tokens")] == 12
    # Non-string attribute values get JSON-encoded
    assert rows[1][cols.index("attributes")]["k"] == "5"


def test_no_spans_inserts_nothing(writer: tuple[ClickHouseWriter, FakeCHClient]) -> None:
    w, fake = writer
    inserted = w.write_trace("default", "demo", {"trace_id": "x", "spans": []})
    assert inserted == 0
    assert fake.inserted == []


def test_missing_trace_id_dropped(writer: tuple[ClickHouseWriter, FakeCHClient]) -> None:
    w, fake = writer
    inserted = w.write_trace("default", "demo", {"spans": [{"span_id": "x"}]})
    assert inserted == 0
    assert fake.inserted == []


def test_invalid_spans_field_dropped(writer: tuple[ClickHouseWriter, FakeCHClient]) -> None:
    w, fake = writer
    inserted = w.write_trace("default", "demo", {"trace_id": "x", "spans": "not-a-list"})
    assert inserted == 0
    assert fake.inserted == []
