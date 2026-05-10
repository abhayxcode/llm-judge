"""GET endpoints for traces + spans, reading from ClickHouse.

The web app calls these to render the traces dashboard. M1 returns enough
to render a list + per-trace detail; pagination, filters, drill-down all
expand here in M2 alongside the production observability surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["traces"])


class TraceSummary(BaseModel):
    trace_id: str
    org_id: str
    project_id: str
    name: str
    first_seen: datetime
    last_seen: datetime
    duration_ms: int
    span_count: int
    root_span_count: int
    status: str
    error: str | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int


class SpanDetail(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    name: str
    start_ts: datetime
    end_ts: datetime | None = None
    duration_ms: int = 0
    status: str
    error: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    gen_ai_system: str = ""
    gen_ai_model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class TraceDetail(BaseModel):
    summary: TraceSummary
    spans: list[SpanDetail]


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


@router.get("/traces", response_model=list[TraceSummary])
def list_traces(
    request: Request,
    project: str = Query("demo", description="Project ID / slug to filter on"),
    limit: int = Query(50, ge=1, le=500),
    since_minutes: int | None = Query(None, ge=1, le=60 * 24 * 30),
    name_contains: str | None = Query(None, max_length=128),
    model: str | None = Query(None, max_length=128),
    status: str | None = Query(None, pattern="^(ok|error)$"),
) -> list[TraceSummary]:
    """List recent traces for a project, newest first.

    Filters (all optional, AND-combined):
    - `since_minutes` — last N minutes of activity.
    - `name_contains` — substring match on the trace name.
    - `model` — match against any span's gen_ai_model on the trace.
    - `status` — `ok` or `error`.
    """
    client = _client(request)
    where = ["project_id = {project:String}"]
    params: dict[str, Any] = {"project": project, "limit": limit}
    if since_minutes is not None:
        where.append("last_seen >= now() - INTERVAL {since:UInt32} MINUTE")
        params["since"] = since_minutes
    if name_contains:
        where.append("position(trace_name, {name_q:String}) > 0")
        params["name_q"] = name_contains
    if status:
        where.append("status = {status:String}")
        params["status"] = status
    if model:
        where.append(
            "trace_id IN (SELECT trace_id FROM spans WHERE project_id = {project:String} "
            "AND gen_ai_model = {model:String})"
        )
        params["model"] = model

    sql = f"""
        SELECT
            trace_id,
            org_id,
            project_id,
            trace_name AS name,
            first_seen,
            last_seen,
            duration_ms,
            span_count,
            root_span_count,
            status,
            error,
            input_tokens,
            output_tokens,
            total_tokens
        FROM v_traces
        WHERE {" AND ".join(where)}
        ORDER BY last_seen DESC
        LIMIT {{limit:UInt32}}
    """
    rows = client.query(sql, parameters=params).named_results()
    return [TraceSummary(**_row(r)) for r in rows]


@router.get("/traces/{trace_id}", response_model=TraceDetail)
def get_trace(
    request: Request,
    trace_id: str,
    project: str = Query("demo"),
) -> TraceDetail:
    client = _client(request)

    summary_rows = list(
        client.query(
            """
            SELECT
                trace_id, org_id, project_id, trace_name AS name,
                first_seen, last_seen, duration_ms, span_count, root_span_count,
                status, error, input_tokens, output_tokens, total_tokens
            FROM v_traces
            WHERE project_id = {project:String} AND trace_id = {trace_id:String}
            """,
            parameters={"project": project, "trace_id": trace_id},
        ).named_results()
    )
    if not summary_rows:
        raise HTTPException(status_code=404, detail="trace not found")

    spans = list(
        client.query(
            """
            SELECT
                span_id, parent_span_id, name,
                start_ts, end_ts, duration_ms,
                status, error,
                attributes,
                gen_ai_system, gen_ai_model,
                input_tokens, output_tokens
            FROM spans
            WHERE project_id = {project:String} AND trace_id = {trace_id:String}
            ORDER BY start_ts ASC
            """,
            parameters={"project": project, "trace_id": trace_id},
        ).named_results()
    )

    return TraceDetail(
        summary=TraceSummary(**_row(summary_rows[0])),
        spans=[SpanDetail(**_row(s)) for s in spans],
    )


def _row(r: dict[str, Any]) -> dict[str, Any]:
    """Coerce ClickHouse types into pydantic-friendly shapes."""
    out: dict[str, Any] = {}
    for k, v in r.items():
        if k == "attributes" and v is None:
            out[k] = {}
        elif isinstance(v, dict):
            out[k] = {str(kk): str(vv) for kk, vv in v.items()}
        else:
            out[k] = v
    return out
