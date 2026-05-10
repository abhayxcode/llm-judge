"""Dataset upload + listing endpoints (M2).

A dataset is a versioned collection of records: input + optional
expected_output + context. Each upload creates a new dataset_version row;
records are immutable after insert.

POST /v1/datasets — create a new version with the given records.
GET  /v1/datasets — list datasets in a project.
GET  /v1/datasets/{slug}/versions/{v}/records — fetch records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from judge_api._ulid import new_ulid
from judge_api.db.engine import get_session
from judge_api.db.models import Dataset, DatasetRecord, DatasetVersion
from judge_api.routes.metrics import _resolve_project

router = APIRouter(prefix="/v1", tags=["datasets"])


class DatasetRecordIn(BaseModel):
    input: dict[str, Any] = Field(..., description="Free-form input payload")
    expected_output: str | None = None
    context: dict[str, Any] | None = None


class DatasetRecordOut(BaseModel):
    id: str
    row_index: int
    input: dict[str, Any]
    expected_output: str | None = None
    context: dict[str, Any] | None = None


class CreateDatasetBody(BaseModel):
    project: str
    slug: str
    name: str
    records: list[DatasetRecordIn]


class DatasetVersionOut(BaseModel):
    id: str
    dataset_id: str
    dataset_slug: str
    version: int
    record_count: int
    created_at: datetime


class DatasetSummary(BaseModel):
    id: str
    slug: str
    name: str
    latest_version: int | None
    record_count: int


@router.post("/datasets", response_model=DatasetVersionOut)
async def create_dataset_version(
    body: CreateDatasetBody,
    session: AsyncSession = Depends(get_session),
) -> DatasetVersionOut:
    if not body.records:
        raise HTTPException(status_code=400, detail="dataset must have at least one record")

    proj = await _resolve_project(session, body.project)

    res = await session.execute(
        select(Dataset).where(Dataset.project_id == proj.id, Dataset.slug == body.slug)
    )
    ds = res.scalar_one_or_none()
    if ds is None:
        ds = Dataset(
            id=new_ulid(),
            project_id=proj.id,
            slug=body.slug,
            name=body.name,
        )
        session.add(ds)
        await session.flush()

    res = await session.execute(
        select(DatasetVersion.version)
        .where(DatasetVersion.dataset_id == ds.id)
        .order_by(DatasetVersion.version.desc())
        .limit(1)
    )
    next_version = (res.scalar_one_or_none() or 0) + 1

    dv = DatasetVersion(
        id=new_ulid(),
        dataset_id=ds.id,
        version=next_version,
        record_count=len(body.records),
    )
    session.add(dv)
    await session.flush()

    for i, r in enumerate(body.records):
        session.add(
            DatasetRecord(
                id=new_ulid(),
                dataset_version_id=dv.id,
                row_index=i,
                input=r.input,
                expected_output=r.expected_output,
                context=r.context,
            )
        )
    await session.commit()
    await session.refresh(dv)

    return DatasetVersionOut(
        id=dv.id,
        dataset_id=ds.id,
        dataset_slug=ds.slug,
        version=dv.version,
        record_count=dv.record_count,
        created_at=dv.created_at,
    )


@router.get("/datasets", response_model=list[DatasetSummary])
async def list_datasets(
    project: str = Query("demo"),
    session: AsyncSession = Depends(get_session),
) -> list[DatasetSummary]:
    proj = await _resolve_project(session, project)
    res = await session.execute(select(Dataset).where(Dataset.project_id == proj.id))
    datasets = list(res.scalars())

    out: list[DatasetSummary] = []
    for d in datasets:
        res2 = await session.execute(
            select(DatasetVersion.version, DatasetVersion.record_count)
            .where(DatasetVersion.dataset_id == d.id)
            .order_by(DatasetVersion.version.desc())
            .limit(1)
        )
        latest = res2.first()
        out.append(
            DatasetSummary(
                id=d.id,
                slug=d.slug,
                name=d.name,
                latest_version=latest[0] if latest else None,
                record_count=latest[1] if latest else 0,
            )
        )
    return out


@router.get("/datasets/records/{record_id}", response_model=DatasetRecordOut)
async def get_dataset_record(
    record_id: str,
    session: AsyncSession = Depends(get_session),
) -> DatasetRecordOut:
    rec = await session.get(DatasetRecord, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"record '{record_id}' not found")
    return DatasetRecordOut(
        id=rec.id,
        row_index=rec.row_index,
        input=rec.input,
        expected_output=rec.expected_output,
        context=rec.context,
    )


@router.get(
    "/datasets/{slug}/versions/{version}/records",
    response_model=list[DatasetRecordOut],
)
async def list_dataset_records(
    slug: str,
    version: int,
    project: str = Query("demo"),
    session: AsyncSession = Depends(get_session),
) -> list[DatasetRecordOut]:
    proj = await _resolve_project(session, project)
    res = await session.execute(
        select(Dataset).where(Dataset.project_id == proj.id, Dataset.slug == slug)
    )
    ds = res.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail=f"dataset '{slug}' not found")
    res = await session.execute(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == ds.id, DatasetVersion.version == version
        )
    )
    dv = res.scalar_one_or_none()
    if dv is None:
        raise HTTPException(status_code=404, detail=f"dataset '{slug}' v{version} not found")

    res = await session.execute(
        select(DatasetRecord)
        .where(DatasetRecord.dataset_version_id == dv.id)
        .order_by(DatasetRecord.row_index.asc())
    )
    return [
        DatasetRecordOut(
            id=r.id,
            row_index=r.row_index,
            input=r.input,
            expected_output=r.expected_output,
            context=r.context,
        )
        for r in res.scalars()
    ]
