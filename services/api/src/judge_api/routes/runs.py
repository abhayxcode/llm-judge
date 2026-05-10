"""Run lifecycle endpoints (M2).

POST /v1/runs — kick off a judge run for {metric@v, dataset@v, judge_config}.
                Enqueues one Arq job per record onto the `evals` Redis stream;
                each worker picks one off, calls the judge, writes the score
                row to ClickHouse and updates the Run row's progress.

GET  /v1/runs?project=…           — list runs newest-first.
GET  /v1/runs/{run_id}            — run summary + progress.
GET  /v1/runs/{run_id}/scores     — per-record scores (joined from CH).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import clickhouse_connect
import redis.asyncio as aioredis
from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from judge_api._ulid import new_ulid
from judge_api.db.engine import get_session
from judge_api.db.models import (
    Dataset,
    DatasetRecord,
    DatasetVersion,
    Metric,
    MetricVersion,
    Run,
)
from judge_api.routes.metrics import _resolve_project

router = APIRouter(prefix="/v1", tags=["runs"])

EVAL_STREAM = "judge:evals"


class CreateRunBody(BaseModel):
    project: str
    name: str = Field(..., max_length=256)
    metric_slug: str
    metric_version: int | None = Field(
        default=None, description="Defaults to latest version for the metric"
    )
    dataset_slug: str
    dataset_version: int | None = None
    judge_config_override: dict[str, Any] | None = None


class RunOut(BaseModel):
    id: str
    project_id: str
    name: str
    status: str
    metric_version_id: str
    dataset_version_id: str
    record_count: int
    completed_count: int
    error_count: int
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ScoreOut(BaseModel):
    trace_id: str
    span_id: str | None = None
    score: float
    score_raw: str
    reasoning: str | None = None
    label: str | None = None
    judge_model: str
    judge_provider: str
    cost_usd: float
    latency_ms: int
    computed_at: datetime


def _ch_client(request: Request) -> Client:
    s = request.app.state.settings
    cached = getattr(request.app.state, "_ch_client", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    client = clickhouse_connect.get_client(
        host=s.ch_host,
        port=s.ch_http_port,
        username=s.ch_user,
        password=s.ch_password,
        database=s.ch_db,
    )
    request.app.state._ch_client = client
    return client


async def _redis(request: Request) -> aioredis.Redis:
    cached = getattr(request.app.state, "_redis", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    client: aioredis.Redis = aioredis.from_url(
        request.app.state.settings.redis_url, decode_responses=False
    )
    request.app.state._redis = client
    return client


def _serialize_run(r: Run) -> RunOut:
    return RunOut(
        id=r.id,
        project_id=r.project_id,
        name=r.name,
        status=r.status,
        metric_version_id=r.metric_version_id,
        dataset_version_id=r.dataset_version_id,
        record_count=r.record_count,
        completed_count=r.completed_count,
        error_count=r.error_count,
        error=r.error,
        started_at=r.started_at,
        finished_at=r.finished_at,
        created_at=r.created_at,
    )


@router.post("/runs", response_model=RunOut)
async def create_run(
    body: CreateRunBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RunOut:
    proj = await _resolve_project(session, body.project)

    res = await session.execute(
        select(Metric).where(Metric.project_id == proj.id, Metric.slug == body.metric_slug)
    )
    metric = res.scalar_one_or_none()
    if metric is None:
        raise HTTPException(404, f"metric '{body.metric_slug}' not found")

    mv_q = select(MetricVersion).where(MetricVersion.metric_id == metric.id)
    if body.metric_version is None:
        mv_q = mv_q.order_by(MetricVersion.version.desc()).limit(1)
    else:
        mv_q = mv_q.where(MetricVersion.version == body.metric_version)
    mv = (await session.execute(mv_q)).scalar_one_or_none()
    if mv is None:
        raise HTTPException(404, "metric version not found")

    res = await session.execute(
        select(Dataset).where(Dataset.project_id == proj.id, Dataset.slug == body.dataset_slug)
    )
    dataset = res.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(404, f"dataset '{body.dataset_slug}' not found")

    dv_q = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id)
    if body.dataset_version is None:
        dv_q = dv_q.order_by(DatasetVersion.version.desc()).limit(1)
    else:
        dv_q = dv_q.where(DatasetVersion.version == body.dataset_version)
    dv = (await session.execute(dv_q)).scalar_one_or_none()
    if dv is None:
        raise HTTPException(404, "dataset version not found")

    if dv.record_count == 0:
        raise HTTPException(400, "dataset version has no records")

    judge_config = dict(mv.ir.get("judge_config", {}))
    if body.judge_config_override:
        judge_config.update(body.judge_config_override)

    run = Run(
        id=new_ulid(),
        project_id=proj.id,
        name=body.name,
        status="queued",
        metric_version_id=mv.id,
        dataset_version_id=dv.id,
        judge_config=judge_config,
        record_count=dv.record_count,
        completed_count=0,
        error_count=0,
    )
    session.add(run)
    await session.commit()

    # Fan out one stream message per record. Workers consume the stream
    # and write score rows to CH; the run's completed_count is bumped by
    # the same worker.
    rec_rows = (
        await session.execute(
            select(DatasetRecord.id, DatasetRecord.row_index)
            .where(DatasetRecord.dataset_version_id == dv.id)
            .order_by(DatasetRecord.row_index.asc())
        )
    ).all()

    redis = await _redis(request)
    pipe = redis.pipeline()
    for rec_id, row_idx in rec_rows:
        payload = {
            "run_id": run.id,
            "record_id": rec_id,
            "row_index": row_idx,
        }
        pipe.xadd(
            EVAL_STREAM,
            {b"payload": json.dumps(payload).encode("utf-8")},
            maxlen=200_000,
            approximate=True,
        )
    await pipe.execute()

    return _serialize_run(run)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    project: str = Query("demo"),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[RunOut]:
    proj = await _resolve_project(session, project)
    res = await session.execute(
        select(Run)
        .where(Run.project_id == proj.id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    )
    return [_serialize_run(r) for r in res.scalars()]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> RunOut:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return _serialize_run(run)


@router.get("/runs/{run_id}/scores", response_model=list[ScoreOut])
async def list_run_scores(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[ScoreOut]:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")

    client = _ch_client(request)
    rows = client.query(
        """
        SELECT
            trace_id, span_id, score, score_raw, reasoning, label,
            judge_model, judge_provider, cost_usd, latency_ms, computed_at
        FROM scores
        WHERE project_id = {project:String}
          AND attributes['run_id'] = {run_id:String}
        ORDER BY computed_at ASC
        """,
        parameters={"project": run.project_id, "run_id": run.id},
    ).named_results()
    return [ScoreOut(**r) for r in rows]
