"""Human label + agreement endpoints (M4).

POST /v1/labels        — create a label for (metric_version, record, user).
                         Idempotent on (metric_version_id, record_id, user_id):
                         a second POST overwrites the existing row.
                         Triggers agreement recompute synchronously (cheap
                         under 10k labels per metric).

GET  /v1/labels        — list labels for project (filterable by metric/user).
GET  /v1/agreement     — current agreement snapshot per (project, metric_version).
POST /v1/agreement/recompute — force recompute (also fired on label POST).

Agreement is computed against the latest judge score per record (joined
from ClickHouse on metric_id + metric_version + attributes['record_id']).
Cohen κ + Pearson + Spearman are judge-vs-human; Fleiss κ is human-only
inter-rater across all labellers for the metric.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from judge_api._ulid import new_ulid
from judge_api.db.engine import get_session
from judge_api.db.models import (
    AgreementMetric,
    DatasetRecord,
    HumanLabel,
    LabelQueueItem,
    Metric,
    MetricVersion,
    User,
)
from judge_api.metrics.agreement import (
    cohen_kappa,
    fleiss_kappa,
    pearson_r,
    spearman_r,
)
from judge_api.routes.metrics import _resolve_project

router = APIRouter(prefix="/v1", tags=["labels"])


class CreateLabelBody(BaseModel):
    project: str
    metric_slug: str
    metric_version: int | None = Field(
        default=None, description="Defaults to latest metric version"
    )
    record_id: str
    user_email: str
    user_name: str | None = None
    score: float
    label: str | None = None
    rationale: str | None = None
    tags: list[str] = Field(default_factory=list)


class LabelOut(BaseModel):
    id: str
    project_id: str
    metric_id: str
    metric_version_id: str
    record_id: str
    user_id: str
    user_email: str
    score: float
    label: str | None
    rationale: str | None
    tags: list[str]
    created_at: datetime


class AgreementOut(BaseModel):
    project_id: str
    metric_id: str
    metric_slug: str
    metric_version_id: str
    metric_version: int
    n_labels: int
    cohen_kappa: float | None
    fleiss_kappa: float | None
    pearson_r: float | None
    spearman_r: float | None
    computed_at: datetime


def _safe_ch_client(request: Request) -> Client | None:
    """Best-effort CH client. Returns None if CH is unreachable so agreement
    recompute can still write a row with judge-vs-human stats nulled out."""
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


async def _get_or_create_user(
    session: AsyncSession, email: str, name: str | None
) -> User:
    res = await session.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if user is not None:
        return user
    user = User(id=new_ulid(), email=email, name=name or email.split("@")[0])
    session.add(user)
    await session.flush()
    return user


async def _resolve_metric_version(
    session: AsyncSession, project_id: str, slug: str, version: int | None
) -> tuple[Metric, MetricVersion]:
    res = await session.execute(
        select(Metric).where(Metric.project_id == project_id, Metric.slug == slug)
    )
    metric = res.scalar_one_or_none()
    if metric is None:
        raise HTTPException(404, f"metric '{slug}' not found")

    q = select(MetricVersion).where(MetricVersion.metric_id == metric.id)
    if version is None:
        q = q.order_by(MetricVersion.version.desc()).limit(1)
    else:
        q = q.where(MetricVersion.version == version)
    mv = (await session.execute(q)).scalar_one_or_none()
    if mv is None:
        raise HTTPException(404, "metric version not found")
    return metric, mv


def _serialize_label(lab: HumanLabel, user_email: str) -> LabelOut:
    return LabelOut(
        id=lab.id,
        project_id=lab.project_id,
        metric_id=lab.metric_id,
        metric_version_id=lab.metric_version_id,
        record_id=lab.record_id,
        user_id=lab.user_id,
        user_email=user_email,
        score=lab.score,
        label=lab.label,
        rationale=lab.rationale,
        tags=lab.tags,
        created_at=lab.created_at,
    )


@router.post("/labels", response_model=LabelOut)
async def create_label(
    body: CreateLabelBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> LabelOut:
    proj = await _resolve_project(session, body.project)
    metric, mv = await _resolve_metric_version(
        session, proj.id, body.metric_slug, body.metric_version
    )

    rec = await session.get(DatasetRecord, body.record_id)
    if rec is None:
        raise HTTPException(404, f"record '{body.record_id}' not found")

    user = await _get_or_create_user(session, body.user_email, body.user_name)

    # Upsert: existing (mv, rec, user) row gets overwritten so re-labeling is
    # ergonomic. Same uniqueness contract as the migration constraint.
    existing = (
        await session.execute(
            select(HumanLabel).where(
                HumanLabel.metric_version_id == mv.id,
                HumanLabel.record_id == body.record_id,
                HumanLabel.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.score = body.score
        existing.label = body.label
        existing.rationale = body.rationale
        existing.tags = body.tags
        lab = existing
    else:
        lab = HumanLabel(
            id=new_ulid(),
            project_id=proj.id,
            metric_id=metric.id,
            metric_version_id=mv.id,
            record_id=body.record_id,
            user_id=user.id,
            score=body.score,
            label=body.label,
            rationale=body.rationale,
            tags=body.tags,
        )
        session.add(lab)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(409, f"label upsert conflict: {e.orig}") from e
    await session.refresh(lab)

    await session.execute(
        update(LabelQueueItem)
        .where(
            LabelQueueItem.project_id == proj.id,
            LabelQueueItem.metric_id == metric.id,
            LabelQueueItem.record_id == body.record_id,
            LabelQueueItem.completed_at.is_(None),
        )
        .values(completed_at=datetime.now())
    )
    await session.commit()

    await _recompute_agreement(
        session=session,
        ch=_safe_ch_client(request),
        project_id=proj.id,
        metric=metric,
        mv=mv,
    )

    return _serialize_label(lab, body.user_email)


@router.get("/labels", response_model=list[LabelOut])
async def list_labels(
    project: str = Query("demo"),
    metric: str | None = Query(None, description="metric slug filter"),
    user_email: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[LabelOut]:
    proj = await _resolve_project(session, project)
    q = (
        select(HumanLabel, User.email)
        .join(User, User.id == HumanLabel.user_id)
        .where(HumanLabel.project_id == proj.id)
        .order_by(HumanLabel.created_at.desc())
        .limit(limit)
    )
    if metric is not None:
        res = await session.execute(
            select(Metric.id).where(Metric.project_id == proj.id, Metric.slug == metric)
        )
        mid = res.scalar_one_or_none()
        if mid is None:
            return []
        q = q.where(HumanLabel.metric_id == mid)
    if user_email is not None:
        q = q.where(User.email == user_email)

    rows = (await session.execute(q)).all()
    return [_serialize_label(lab, email) for lab, email in rows]


@router.get("/agreement", response_model=AgreementOut | None)
async def get_agreement(
    project: str = Query("demo"),
    metric: str = Query(..., description="metric slug"),
    version: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> AgreementOut | None:
    proj = await _resolve_project(session, project)
    metric_row, mv = await _resolve_metric_version(session, proj.id, metric, version)

    res = await session.execute(
        select(AgreementMetric).where(
            AgreementMetric.project_id == proj.id,
            AgreementMetric.metric_version_id == mv.id,
        )
    )
    snap = res.scalar_one_or_none()
    if snap is None:
        return None
    return AgreementOut(
        project_id=snap.project_id,
        metric_id=snap.metric_id,
        metric_slug=metric_row.slug,
        metric_version_id=snap.metric_version_id,
        metric_version=mv.version,
        n_labels=snap.n_labels,
        cohen_kappa=snap.cohen_kappa,
        fleiss_kappa=snap.fleiss_kappa,
        pearson_r=snap.pearson_r,
        spearman_r=snap.spearman_r,
        computed_at=snap.computed_at,
    )


@router.post("/agreement/recompute", response_model=AgreementOut)
async def post_recompute_agreement(
    body: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgreementOut:
    project = body.get("project", "demo")
    metric_slug = body.get("metric")
    if not metric_slug:
        raise HTTPException(400, "metric is required")
    version = body.get("version")

    proj = await _resolve_project(session, project)
    metric_row, mv = await _resolve_metric_version(session, proj.id, metric_slug, version)
    snap = await _recompute_agreement(
        session=session,
        ch=_safe_ch_client(request),
        project_id=proj.id,
        metric=metric_row,
        mv=mv,
    )
    return AgreementOut(
        project_id=snap.project_id,
        metric_id=snap.metric_id,
        metric_slug=metric_row.slug,
        metric_version_id=snap.metric_version_id,
        metric_version=mv.version,
        n_labels=snap.n_labels,
        cohen_kappa=snap.cohen_kappa,
        fleiss_kappa=snap.fleiss_kappa,
        pearson_r=snap.pearson_r,
        spearman_r=snap.spearman_r,
        computed_at=snap.computed_at,
    )


async def _recompute_agreement(
    *,
    session: AsyncSession,
    ch: Client | None,
    project_id: str,
    metric: Metric,
    mv: MetricVersion,
) -> AgreementMetric:
    """Compute and upsert an AgreementMetric row.

    For each (record, user) human label, fetch the latest judge score from
    CH (project_id, metric_id=slug, metric_version=int, attrs.record_id).
    Build (judge, human) pairs for Cohen κ / Pearson / Spearman; build
    per-record human-only matrices for Fleiss κ.
    """
    res = await session.execute(
        select(HumanLabel.record_id, HumanLabel.user_id, HumanLabel.score)
        .where(HumanLabel.metric_version_id == mv.id)
    )
    label_rows = res.all()
    n_labels = len(label_rows)

    # Per-record list of human scores → Fleiss matrix.
    by_record: dict[str, list[float]] = {}
    user_record_scores: dict[tuple[str, str], float] = {}
    for record_id, user_id, score in label_rows:
        by_record.setdefault(record_id, []).append(score)
        user_record_scores[(user_id, record_id)] = score

    judge_by_record: dict[str, float] = {}
    if ch is not None and label_rows:
        record_ids = list(by_record.keys())
        rows = ch.query(
            """
            SELECT
                attributes['record_id'] AS record_id,
                argMax(score, computed_at) AS judge_score
            FROM scores
            WHERE project_id = {project:String}
              AND metric_id = {metric:String}
              AND metric_version = {version:String}
              AND attributes['record_id'] IN {ids:Array(String)}
            GROUP BY record_id
            """,
            parameters={
                "project": project_id,
                "metric": metric.slug,
                "version": str(mv.version),
                "ids": record_ids,
            },
        ).named_results()
        for r in rows:
            judge_by_record[str(r["record_id"])] = float(r["judge_score"])

    # Build judge-vs-human pairs (one row per label, judge score broadcast).
    judge_xs: list[float] = []
    human_ys: list[float] = []
    for record_id, _user_id, score in label_rows:
        j = judge_by_record.get(record_id)
        if j is not None:
            judge_xs.append(j)
            human_ys.append(score)

    cohen = cohen_kappa(judge_xs, human_ys) if len(judge_xs) >= 2 else None
    pearson = pearson_r(judge_xs, human_ys) if len(judge_xs) >= 2 else None
    spearman = spearman_r(judge_xs, human_ys) if len(judge_xs) >= 2 else None

    # Fleiss κ across human raters: only records with >= 2 humans count.
    fleiss = None
    multi_rater = [scores for scores in by_record.values() if len(scores) >= 2]
    if multi_rater:
        # Equalize rater count by truncating each row to the min row length.
        # Items with fewer raters than max simply contribute fewer raters.
        n_raters = min(len(s) for s in multi_rater)
        if n_raters >= 2 and len(multi_rater) >= 2:
            trimmed = [s[:n_raters] for s in multi_rater]
            fleiss = fleiss_kappa(trimmed)

    res = await session.execute(
        select(AgreementMetric).where(
            AgreementMetric.project_id == project_id,
            AgreementMetric.metric_version_id == mv.id,
        )
    )
    snap = res.scalar_one_or_none()
    if snap is None:
        snap = AgreementMetric(
            id=new_ulid(),
            project_id=project_id,
            metric_id=metric.id,
            metric_version_id=mv.id,
            n_labels=n_labels,
            cohen_kappa=cohen,
            fleiss_kappa=fleiss,
            pearson_r=pearson,
            spearman_r=spearman,
            computed_at=datetime.now(),
        )
        session.add(snap)
    else:
        snap.n_labels = n_labels
        snap.cohen_kappa = cohen
        snap.fleiss_kappa = fleiss
        snap.pearson_r = pearson
        snap.spearman_r = spearman
        snap.computed_at = datetime.now()
    await session.commit()
    await session.refresh(snap)
    return snap
