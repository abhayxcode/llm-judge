"""SQLAlchemy models — transactional metadata in Postgres.

ClickHouse stores high-volume span/score data; Postgres stores everything
that needs ACID + relations: orgs, projects, RBAC, datasets, metric defs,
prompts, runs, budgets, audit log.

M1 only declares orgs/projects/api_keys. Datasets, metric defs, prompts,
eval runs land in M2 alongside the eval engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, func
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
