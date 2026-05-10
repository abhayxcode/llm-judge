"""Metric registration + lookup endpoints (M2).

POST /v1/metrics — register a metric IR. If hash is new for the metric
slug, a new `metric_versions` row is inserted with version = max+1.
If hash matches an existing version, return that version (idempotent).

GET /v1/metrics?project=… — list metrics with their latest version.
GET /v1/metrics/{slug}/versions/{v}?project=… — fetch a specific IR.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from judge_api._ulid import new_ulid
from judge_api.db.engine import get_session
from judge_api.db.models import Metric, MetricVersion, Project
from judge_api.metrics import MetricIR

router = APIRouter(prefix="/v1", tags=["metrics"])


class MetricVersionOut(BaseModel):
    id: str
    metric_id: str
    metric_slug: str
    version: int
    hash: str
    ir: dict[str, Any]
    created_at: datetime


class MetricSummary(BaseModel):
    id: str
    slug: str
    name: str
    scoring_type: str
    latest_version: int | None
    latest_hash: str | None


class RegisterMetricBody(BaseModel):
    project: str
    ir: MetricIR


async def _resolve_project(session: AsyncSession, slug_or_id: str) -> Project:
    """Resolve `project` query param to a Project row.

    M1 bootstrap stamps a project named `demo`; tests/SDK pass either the
    slug or the ULID. We try id first (ULIDs are uppercase, exact len 26)
    and fall back to slug.
    """
    if len(slug_or_id) == 26 and slug_or_id.isupper():
        row = await session.get(Project, slug_or_id)
        if row is not None:
            return row
    res = await session.execute(select(Project).where(Project.slug == slug_or_id))
    project = res.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"project '{slug_or_id}' not found")
    return project


@router.post("/metrics", response_model=MetricVersionOut)
async def register_metric(
    body: RegisterMetricBody,
    session: AsyncSession = Depends(get_session),
) -> MetricVersionOut:
    project = await _resolve_project(session, body.project)
    ir = body.ir
    content_hash = ir.content_hash()

    # Find or create the parent Metric row.
    res = await session.execute(
        select(Metric).where(Metric.project_id == project.id, Metric.slug == ir.id)
    )
    metric = res.scalar_one_or_none()
    if metric is None:
        metric = Metric(
            id=new_ulid(),
            project_id=project.id,
            slug=ir.id,
            name=ir.name or ir.id,
            scoring_type=ir.scoring_type.value,
        )
        session.add(metric)
        await session.flush()

    # Idempotent: same hash → existing version.
    res = await session.execute(
        select(MetricVersion).where(
            MetricVersion.metric_id == metric.id, MetricVersion.hash == content_hash
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        await session.commit()
        return MetricVersionOut(
            id=existing.id,
            metric_id=metric.id,
            metric_slug=metric.slug,
            version=existing.version,
            hash=existing.hash,
            ir=existing.ir,
            created_at=existing.created_at,
        )

    res = await session.execute(
        select(MetricVersion.version)
        .where(MetricVersion.metric_id == metric.id)
        .order_by(MetricVersion.version.desc())
        .limit(1)
    )
    next_version = (res.scalar_one_or_none() or 0) + 1

    mv = MetricVersion(
        id=new_ulid(),
        metric_id=metric.id,
        version=next_version,
        hash=content_hash,
        ir=ir.model_dump(mode="json"),
    )
    session.add(mv)
    await session.commit()
    await session.refresh(mv)

    return MetricVersionOut(
        id=mv.id,
        metric_id=metric.id,
        metric_slug=metric.slug,
        version=mv.version,
        hash=mv.hash,
        ir=mv.ir,
        created_at=mv.created_at,
    )


@router.get("/metrics", response_model=list[MetricSummary])
async def list_metrics(
    project: str = Query("demo"),
    session: AsyncSession = Depends(get_session),
) -> list[MetricSummary]:
    proj = await _resolve_project(session, project)
    res = await session.execute(select(Metric).where(Metric.project_id == proj.id))
    metrics = list(res.scalars())

    out: list[MetricSummary] = []
    for m in metrics:
        res2 = await session.execute(
            select(MetricVersion.version, MetricVersion.hash)
            .where(MetricVersion.metric_id == m.id)
            .order_by(MetricVersion.version.desc())
            .limit(1)
        )
        latest = res2.first()
        out.append(
            MetricSummary(
                id=m.id,
                slug=m.slug,
                name=m.name,
                scoring_type=m.scoring_type,
                latest_version=latest[0] if latest else None,
                latest_hash=latest[1] if latest else None,
            )
        )
    return out


@router.get("/metrics/{slug}/versions/{version}", response_model=MetricVersionOut)
async def get_metric_version(
    slug: str,
    version: int,
    project: str = Query("demo"),
    session: AsyncSession = Depends(get_session),
) -> MetricVersionOut:
    proj = await _resolve_project(session, project)
    res = await session.execute(
        select(Metric).where(Metric.project_id == proj.id, Metric.slug == slug)
    )
    metric = res.scalar_one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail=f"metric '{slug}' not found")

    res2 = await session.execute(
        select(MetricVersion).where(
            MetricVersion.metric_id == metric.id, MetricVersion.version == version
        )
    )
    mv = res2.scalar_one_or_none()
    if mv is None:
        raise HTTPException(status_code=404, detail=f"metric '{slug}' v{version} not found")

    return MetricVersionOut(
        id=mv.id,
        metric_id=metric.id,
        metric_slug=metric.slug,
        version=mv.version,
        hash=mv.hash,
        ir=mv.ir,
        created_at=mv.created_at,
    )
