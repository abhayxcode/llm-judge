"""SQLAlchemy models — transactional metadata in Postgres.

ClickHouse stores high-volume span/score data; Postgres stores everything
that needs ACID + relations: orgs, projects, RBAC, datasets, metric defs,
prompts, runs, budgets, audit log.

M2 adds metric IR + dataset versioning + runs alongside the eval engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _ulid_pk() -> Mapped[str]:
    """Primary key column declaration helper. ULIDs are 26 chars."""
    return mapped_column(String(26), primary_key=True)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = _ulid_pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    projects: Mapped[list[Project]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = _ulid_pk()
    org_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Per-project settings: redaction, retention, sampling, integrations.
    # JSONB in PG; SQLAlchemy maps to JSON.
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    org: Mapped[Org] = relationship(back_populates="projects")
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Store sha256 hex digest of the plaintext key, never the plaintext.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # First 8 chars of plaintext shown in UI for identification.
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="api_keys")


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    scoring_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    versions: Mapped[list[MetricVersion]] = relationship(
        back_populates="metric", cascade="all, delete-orphan"
    )


class MetricVersion(Base):
    """Immutable, content-addressed snapshot of a metric definition.

    `hash` is sha256 of the canonical JSON of the IR; same content → same hash.
    `version` is a monotonic 1-based int per metric, assigned at insert time.
    """

    __tablename__ = "metric_versions"

    id: Mapped[str] = _ulid_pk()
    metric_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ir: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    metric: Mapped[Metric] = relationship(back_populates="versions")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)

    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = _ulid_pk()
    dataset_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    records: Mapped[list[DatasetRecord]] = relationship(
        back_populates="dataset_version", cascade="all, delete-orphan"
    )


class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    id: Mapped[str] = _ulid_pk()
    dataset_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="records")


class Run(Base):
    """One `judge run` invocation. Status: queued → running → done|failed.

    Score rows live in CH; this row holds run-level rollups + status so the
    UI can render progress without scanning CH.
    """

    __tablename__ = "runs"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    metric_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metric_versions.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    judge_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _ulid_pk()
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HumanLabel(Base):
    """One labeller's score for one (metric_version, record) pair.

    Uniqueness is on (metric_version_id, record_id, user_id); inter-rater
    agreement is computed across all labellers for the same row.
    """

    __tablename__ = "human_labels"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    metric_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metric_versions.id", ondelete="CASCADE"), nullable=False
    )
    record_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("dataset_records.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgreementMetric(Base):
    """Latest agreement snapshot per (project, metric_version).

    Recomputed on every label write (incrementally cheap for n < 10k);
    full nightly recompute is a separate job (deferred to M5).
    """

    __tablename__ = "agreement_metrics"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    metric_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metric_versions.id", ondelete="CASCADE"), nullable=False
    )
    n_labels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cohen_kappa: Mapped[float | None] = mapped_column(Float, nullable=True)
    fleiss_kappa: Mapped[float | None] = mapped_column(Float, nullable=True)
    pearson_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    spearman_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LabelQueueItem(Base):
    """One queued candidate record for human labelling.

    Built by the active-learning sampler; surfaced via /v1/queue. Multiple
    strategies write rows here; uniqueness on (project, metric, record)
    keeps the queue de-duplicated across strategy runs.
    """

    __tablename__ = "label_queue"

    id: Mapped[str] = _ulid_pk()
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    record_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("dataset_records.id", ondelete="CASCADE"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    """Best-effort audit trail. Heavy actions also write to CH `audit_log_ch`
    for analytics; this table is the canonical record for admin queries."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
