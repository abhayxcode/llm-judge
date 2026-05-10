"""Active-learning queue endpoints (M4).

POST /v1/queue/refresh — recompute the queue for (project, metric) using a
                          weighted blend of strategies. Old un-claimed rows
                          are wiped first; un-claimed rows that were
                          regenerated keep their priority.

GET  /v1/queue          — list pending queue items (ordered by priority desc).
POST /v1/queue/{id}/claim    — assign to a user.
POST /v1/queue/{id}/skip     — drop without labeling (sets completed_at, reason).

Strategies (M4):
  - low_confidence : judge score is mid-scale (near threshold) OR the CH
                     `score_raw` reasoning hints at uncertainty.
  - drift_outlier  : input length is far from project median (proxy for
                     embedding distance until we wire FAISS in M5/P2).
  - ensemble_disagreement : stub. Returns nothing until ensembles ship in P2.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from judge_api._ulid import new_ulid
from judge_api.db.engine import get_session
from judge_api.db.models import (
    DatasetRecord,
    DatasetVersion,
    HumanLabel,
    LabelQueueItem,
    Metric,
    MetricVersion,
    Run,
    User,
)
from judge_api.routes.metrics import _resolve_project

router = APIRouter(prefix="/v1", tags=["queue"])

DEFAULT_QUEUE_SIZE = 50
DEFAULT_WEIGHTS = {"low_confidence": 0.6, "drift_outlier": 0.4}


class RefreshBody(BaseModel):
    project: str
    metric: str = Field(..., description="metric slug")
    queue_size: int = DEFAULT_QUEUE_SIZE
    weights: dict[str, float] | None = None


class QueueOut(BaseModel):
    id: str
    project_id: str
    metric_id: str
    record_id: str
    strategy: str
    priority: float
    reason: str | None
    claimed_by: str | None
    claimed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class QueueRefreshOut(BaseModel):
    queue_size: int
    inserted: int
    strategies_used: list[str]


class ClaimBody(BaseModel):
    user_email: str
    user_name: str | None = None


def _safe_ch_client(request: Request) -> Client | None:
    cached = getattr(request.app.state, "_ch_client", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    s = request.app.state.settings
    try:
        client = clickhouse_connect.get_client(
            host=s.ch_host,
            port=s.ch_http_port,
            username=s.ch_user,
            password=s.ch_password,
            database=s.ch_db,
        )
    except Exception:
        return None
    request.app.state._ch_client = client
    return client


def _serialize(q: LabelQueueItem) -> QueueOut:
    return QueueOut(
        id=q.id,
        project_id=q.project_id,
        metric_id=q.metric_id,
        record_id=q.record_id,
        strategy=q.strategy,
        priority=q.priority,
        reason=q.reason,
        claimed_by=q.claimed_by,
        claimed_at=q.claimed_at,
        completed_at=q.completed_at,
        created_at=q.created_at,
    )


@router.post("/queue/refresh", response_model=QueueRefreshOut)
async def refresh_queue(
    body: RefreshBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> QueueRefreshOut:
    proj = await _resolve_project(session, body.project)
    res = await session.execute(
        select(Metric).where(Metric.project_id == proj.id, Metric.slug == body.metric)
    )
    metric = res.scalar_one_or_none()
    if metric is None:
        raise HTTPException(404, f"metric '{body.metric}' not found")

    weights = body.weights or DEFAULT_WEIGHTS

    # Wipe un-claimed, un-completed rows; claimed-in-progress rows survive.
    await session.execute(
        delete(LabelQueueItem).where(
            LabelQueueItem.project_id == proj.id,
            LabelQueueItem.metric_id == metric.id,
            LabelQueueItem.claimed_by.is_(None),
            LabelQueueItem.completed_at.is_(None),
        )
    )

    # Candidate pool: dataset records that have NEVER been labelled by any
    # human for this metric (any version). Limit to 5000 to bound work.
    candidates = await _candidate_records(session, proj.id, metric.id, limit=5000)
    if not candidates:
        await session.commit()
        return QueueRefreshOut(queue_size=0, inserted=0, strategies_used=[])

    ch = _safe_ch_client(request)
    judge_scores = await _latest_judge_scores(ch, proj.id, metric.slug, candidates)

    strategies_used: list[str] = []
    by_record_priority: dict[str, tuple[str, float, str | None]] = {}

    if weights.get("low_confidence", 0) > 0:
        strategies_used.append("low_confidence")
        for rec_id, score in judge_scores.items():
            distance = _distance_from_decision_boundary(score)
            priority = weights["low_confidence"] * (1.0 - distance)
            reason = f"judge score {score:.2f} near threshold (Δ={distance:.2f})"
            _accumulate(by_record_priority, rec_id, "low_confidence", priority, reason)

    if weights.get("drift_outlier", 0) > 0:
        strategies_used.append("drift_outlier")
        record_inputs = await _fetch_record_lengths(session, candidates)
        if record_inputs:
            lengths = list(record_inputs.values())
            median = statistics.median(lengths)
            mad = max(1.0, _median_abs_deviation(lengths, median))
            for rec_id, length in record_inputs.items():
                z = abs(length - median) / mad
                # Squash via tanh so super-long outliers don't dominate.
                priority = weights["drift_outlier"] * math.tanh(z / 3.0)
                reason = f"|len - median| = {abs(length - median):.0f} chars (z≈{z:.2f})"
                _accumulate(by_record_priority, rec_id, "drift_outlier", priority, reason)

    # ensemble_disagreement: stub — left out until P2 ensembles ship.

    ranked = sorted(
        by_record_priority.items(), key=lambda kv: kv[1][1], reverse=True
    )[: body.queue_size]

    inserted = 0
    for rec_id, (strategy, priority, reason) in ranked:
        session.add(
            LabelQueueItem(
                id=new_ulid(),
                project_id=proj.id,
                metric_id=metric.id,
                record_id=rec_id,
                strategy=strategy,
                priority=priority,
                reason=reason,
            )
        )
        inserted += 1
    await session.commit()
    return QueueRefreshOut(
        queue_size=inserted, inserted=inserted, strategies_used=strategies_used
    )


@router.get("/queue", response_model=list[QueueOut])
async def list_queue(
    project: str = Query("demo"),
    metric: str = Query(..., description="metric slug"),
    limit: int = Query(50, ge=1, le=500),
    pending_only: bool = Query(True),
    session: AsyncSession = Depends(get_session),
) -> list[QueueOut]:
    proj = await _resolve_project(session, project)
    res = await session.execute(
        select(Metric).where(Metric.project_id == proj.id, Metric.slug == metric)
    )
    metric_row = res.scalar_one_or_none()
    if metric_row is None:
        return []
    q = (
        select(LabelQueueItem)
        .where(
            LabelQueueItem.project_id == proj.id,
            LabelQueueItem.metric_id == metric_row.id,
        )
        .order_by(LabelQueueItem.priority.desc(), LabelQueueItem.created_at.desc())
        .limit(limit)
    )
    if pending_only:
        q = q.where(LabelQueueItem.completed_at.is_(None))
    rows = list((await session.execute(q)).scalars())
    return [_serialize(r) for r in rows]


@router.post("/queue/{queue_id}/claim", response_model=QueueOut)
async def claim_queue_item(
    queue_id: str,
    body: ClaimBody,
    session: AsyncSession = Depends(get_session),
) -> QueueOut:
    item = await session.get(LabelQueueItem, queue_id)
    if item is None:
        raise HTTPException(404, "queue item not found")

    res = await session.execute(select(User).where(User.email == body.user_email))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(
            id=new_ulid(),
            email=body.user_email,
            name=body.user_name or body.user_email.split("@")[0],
        )
        session.add(user)
        await session.flush()

    if item.claimed_by and item.claimed_by != user.id:
        raise HTTPException(409, "queue item already claimed by another user")

    item.claimed_by = user.id
    item.claimed_at = datetime.now()
    await session.commit()
    await session.refresh(item)
    return _serialize(item)


@router.post("/queue/{queue_id}/skip", response_model=QueueOut)
async def skip_queue_item(
    queue_id: str,
    body: dict[str, Any] | None = None,
    session: AsyncSession = Depends(get_session),
) -> QueueOut:
    item = await session.get(LabelQueueItem, queue_id)
    if item is None:
        raise HTTPException(404, "queue item not found")
    item.completed_at = datetime.now()
    if body and "reason" in body:
        item.reason = (item.reason or "") + f" | skipped: {body['reason']}"
    await session.commit()
    await session.refresh(item)
    return _serialize(item)


async def _candidate_records(
    session: AsyncSession, project_id: str, metric_id: str, *, limit: int
) -> list[str]:
    """Records with at least one judge score for this metric — i.e. records
    that have actually been seen by the judge — minus any record that
    already has a human label for this metric."""
    # Records present in any run for this project: derive via dataset_version
    # → dataset_records that the metric's runs cover. Simpler: any record in
    # any dataset version associated with a run that targeted this metric.
    res = await session.execute(
        select(DatasetRecord.id)
        .join(
            DatasetVersion, DatasetVersion.id == DatasetRecord.dataset_version_id
        )
        .join(Run, Run.dataset_version_id == DatasetVersion.id)
        .join(MetricVersion, MetricVersion.id == Run.metric_version_id)
        .where(
            Run.project_id == project_id,
            MetricVersion.metric_id == metric_id,
        )
        .distinct()
        .limit(limit)
    )
    seen_record_ids = [row[0] for row in res.all()]
    if not seen_record_ids:
        return []

    res = await session.execute(
        select(HumanLabel.record_id).where(
            HumanLabel.project_id == project_id, HumanLabel.metric_id == metric_id
        )
    )
    labelled = {row[0] for row in res.all()}
    return [r for r in seen_record_ids if r not in labelled]


async def _latest_judge_scores(
    ch: Client | None, project_id: str, metric_slug: str, record_ids: list[str]
) -> dict[str, float]:
    if ch is None or not record_ids:
        return {}
    rows = ch.query(
        """
        SELECT
            attributes['record_id'] AS record_id,
            argMax(score, computed_at) AS judge_score
        FROM scores
        WHERE project_id = {project:String}
          AND metric_id = {metric:String}
          AND attributes['record_id'] IN {ids:Array(String)}
        GROUP BY record_id
        """,
        parameters={
            "project": project_id,
            "metric": metric_slug,
            "ids": record_ids,
        },
    ).named_results()
    return {str(r["record_id"]): float(r["judge_score"]) for r in rows}


async def _fetch_record_lengths(
    session: AsyncSession, record_ids: list[str]
) -> dict[str, int]:
    if not record_ids:
        return {}
    res = await session.execute(
        select(DatasetRecord.id, DatasetRecord.input).where(
            DatasetRecord.id.in_(record_ids)
        )
    )
    out: dict[str, int] = {}
    for rid, inp in res.all():
        out[rid] = _input_length(inp)
    return out


def _input_length(inp: dict[str, Any] | None) -> int:
    """Cheap proxy for embedding distance: total char count of stringy fields."""
    if not inp:
        return 0
    total = 0
    for v in inp.values():
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, list):
            total += sum(len(s) for s in v if isinstance(s, str))
        elif isinstance(v, dict):
            total += _input_length(v)
    return total


def _distance_from_decision_boundary(score: float) -> float:
    """Map a judge score to its distance from the nearest decision threshold.

    Pointwise scales we ship: 1-5 (faithfulness, ordinal). Boundary points are
    the half-way marks (1.5, 2.5, 3.5, 4.5). Pairwise: 0/0.5/1; boundary at
    0.25 / 0.75. Returns 0 at the boundary, 1 at the extreme. Conservative
    fallback: treat unknown ranges as continuous in [0, 1].
    """
    if 0.0 <= score <= 1.0:
        # 0/0.5/1 pairwise → distances {0.5, 0, 0.5}; rescale to [0, 1].
        return abs(score - 0.5) * 2.0
    if 1.0 <= score <= 5.0:
        # Distance to nearest 0.5 boundary, normalized to 0.5.
        nearest_int = round(score)
        return min(1.0, abs(score - nearest_int) * 2.0)
    return abs(score - 0.5) * 2.0


def _median_abs_deviation(values: Iterable[float], median: float) -> float:
    deviations = [abs(v - median) for v in values]
    if not deviations:
        return 1.0
    return statistics.median(deviations)


def _accumulate(
    acc: dict[str, tuple[str, float, str | None]],
    rec_id: str,
    strategy: str,
    priority: float,
    reason: str | None,
) -> None:
    """Keep the highest-priority strategy per record."""
    existing = acc.get(rec_id)
    if existing is None or priority > existing[1]:
        acc[rec_id] = (strategy, priority, reason)
