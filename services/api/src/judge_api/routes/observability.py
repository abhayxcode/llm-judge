"""Production observability surface — aggregations over the spans table.

GET /v1/observability/stats — single shot for the headline cards:
    {
      "trace_count": <int>,
      "error_count": <int>,
      "p50_ms": <float>, "p95_ms": <float>,
      "input_tokens": <int>, "output_tokens": <int>,
      "estimated_cost_usd": <float>,
      "since": <iso>
    }

GET /v1/observability/timeseries?bucket=1m|5m|1h — bucketed counts/
latencies over the window. Returns:
    {"bucket": "1m", "points": [{"ts": ..., "count": ..., "p95_ms": ...}]}

GET /v1/observability/score_distribution — histogram of recent scores
across all metrics in the project (used for the live dashboard chart).

All endpoints are uncached and read directly from ClickHouse — fine
for M3 since the spans+scores tables are designed for this query
shape. Materialized views can land later if write/read ratio shifts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/observability", tags=["observability"])


def _client(request: Request) -> Client:
    settings = request.app.state.settings
    cached = getattr(request.app.state, "_ch_client", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    client = clickhouse_connect.get_client(
        host=settings.ch_host,
        port=settings.ch_http_port,
        username=settings.ch_user,
        password=settings.ch_password,
        database=settings.ch_db,
    )
    request.app.state._ch_client = client
    return client


class Stats(BaseModel):
    project: str
    since_minutes: int
    trace_count: int
    error_count: int
    p50_ms: float
    p95_ms: float
    input_tokens: int
    output_tokens: int


class TimeseriesPoint(BaseModel):
    ts: datetime
    count: int
    error_count: int
    p50_ms: float
    p95_ms: float


class Timeseries(BaseModel):
    bucket: str
    project: str
    points: list[TimeseriesPoint]


class ScoreBucket(BaseModel):
    metric_id: str
    bucket: str  # "0.0-0.2" etc.
    count: int


@router.get("/stats", response_model=Stats)
def get_stats(
    request: Request,
    project: str = Query("demo"),
    since_minutes: int = Query(60, ge=1, le=60 * 24 * 30),
) -> Stats:
    client = _client(request)
    row = (
        client.query(
            """
            SELECT
                count() AS trace_count,
                countIf(status = 'error') AS error_count,
                quantile(0.5)(duration_ms) AS p50_ms,
                quantile(0.95)(duration_ms) AS p95_ms,
                sum(input_tokens) AS input_tokens,
                sum(output_tokens) AS output_tokens
            FROM v_traces
            WHERE project_id = {project:String}
              AND last_seen >= now() - INTERVAL {since:UInt32} MINUTE
            """,
            parameters={"project": project, "since": since_minutes},
        )
        .named_results()
    )
    r = next(iter(row), {})
    return Stats(
        project=project,
        since_minutes=since_minutes,
        trace_count=int(r.get("trace_count", 0)),
        error_count=int(r.get("error_count", 0)),
        p50_ms=float(r.get("p50_ms") or 0.0),
        p95_ms=float(r.get("p95_ms") or 0.0),
        input_tokens=int(r.get("input_tokens", 0)),
        output_tokens=int(r.get("output_tokens", 0)),
    )


_BUCKETS = {"1m": ("toStartOfMinute", 60), "5m": ("toStartOfFiveMinute", 60 * 5), "1h": ("toStartOfHour", 60 * 60)}


@router.get("/timeseries", response_model=Timeseries)
def get_timeseries(
    request: Request,
    project: str = Query("demo"),
    bucket: str = Query("1m", pattern="^(1m|5m|1h)$"),
    since_minutes: int = Query(60, ge=1, le=60 * 24 * 30),
) -> Timeseries:
    client = _client(request)
    fn, _ = _BUCKETS[bucket]
    sql = f"""
        SELECT
            {fn}(last_seen) AS ts,
            count() AS count,
            countIf(status = 'error') AS error_count,
            quantile(0.5)(duration_ms) AS p50_ms,
            quantile(0.95)(duration_ms) AS p95_ms
        FROM v_traces
        WHERE project_id = {{project:String}}
          AND last_seen >= now() - INTERVAL {{since:UInt32}} MINUTE
        GROUP BY ts
        ORDER BY ts ASC
    """
    rows = client.query(
        sql, parameters={"project": project, "since": since_minutes}
    ).named_results()
    points = [
        TimeseriesPoint(
            ts=r["ts"],
            count=int(r["count"]),
            error_count=int(r["error_count"]),
            p50_ms=float(r.get("p50_ms") or 0.0),
            p95_ms=float(r.get("p95_ms") or 0.0),
        )
        for r in rows
    ]
    return Timeseries(bucket=bucket, project=project, points=points)


@router.get("/score_distribution", response_model=list[ScoreBucket])
def score_distribution(
    request: Request,
    project: str = Query("demo"),
    since_minutes: int = Query(60 * 24, ge=1),
) -> list[ScoreBucket]:
    """Histogram of normalized scores per metric over the window.

    Buckets: 0.0–0.2, 0.2–0.4, 0.4–0.6, 0.6–0.8, 0.8–1.0.
    """
    client = _client(request)
    rows = client.query(
        """
        SELECT
            metric_id,
            CASE
                WHEN score < 0.2 THEN '0.0-0.2'
                WHEN score < 0.4 THEN '0.2-0.4'
                WHEN score < 0.6 THEN '0.4-0.6'
                WHEN score < 0.8 THEN '0.6-0.8'
                ELSE '0.8-1.0'
            END AS bucket,
            count() AS count
        FROM scores
        WHERE project_id = {project:String}
          AND computed_at >= now() - INTERVAL {since:UInt32} MINUTE
        GROUP BY metric_id, bucket
        ORDER BY metric_id, bucket
        """,
        parameters={"project": project, "since": since_minutes},
    ).named_results()
    return [
        ScoreBucket(metric_id=r["metric_id"], bucket=r["bucket"], count=int(r["count"]))
        for r in rows
    ]


def _coerce(_x: Any) -> Any:
    return _x  # placeholder for future shape coercion
