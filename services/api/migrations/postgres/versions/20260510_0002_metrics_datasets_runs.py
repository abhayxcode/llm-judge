"""metrics, metric_versions, datasets, dataset_versions, dataset_records, runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-10

M2 surface: metric IR storage (content-addressed via hash), dataset versioning,
and runs (one row per `judge run` invocation). Scores themselves live in
ClickHouse for OLAP; this table holds run-level rollups + status.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("scoring_type", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "slug", name="uq_metrics_project_id_slug"),
    )
    op.create_index("ix_metrics_project_id", "metrics", ["project_id"])

    op.create_table(
        "metric_versions",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "metric_id",
            sa.String(length=26),
            sa.ForeignKey("metrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("ir", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("metric_id", "version", name="uq_metric_versions_metric_id_version"),
        sa.UniqueConstraint("metric_id", "hash", name="uq_metric_versions_metric_id_hash"),
    )
    op.create_index("ix_metric_versions_metric_id", "metric_versions", ["metric_id"])

    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "slug", name="uq_datasets_project_id_slug"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=26),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dataset_id", "version", name="uq_dataset_versions_dataset_id_version"
        ),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])

    op.create_table(
        "dataset_records",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(length=26),
            sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer, nullable=False),
        sa.Column("input", sa.JSON, nullable=False),
        sa.Column("expected_output", sa.Text, nullable=True),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dataset_version_id",
            "row_index",
            name="uq_dataset_records_dataset_version_id_row_index",
        ),
    )
    op.create_index(
        "ix_dataset_records_dataset_version_id", "dataset_records", ["dataset_version_id"]
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column(
            "metric_version_id",
            sa.String(length=26),
            sa.ForeignKey("metric_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_version_id",
            sa.String(length=26),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("judge_config", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_runs_project_id_created_at", "runs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_project_id_created_at", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_dataset_records_dataset_version_id", table_name="dataset_records")
    op.drop_table("dataset_records")
    op.drop_index("ix_dataset_versions_dataset_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index("ix_datasets_project_id", table_name="datasets")
    op.drop_table("datasets")
    op.drop_index("ix_metric_versions_metric_id", table_name="metric_versions")
    op.drop_table("metric_versions")
    op.drop_index("ix_metrics_project_id", table_name="metrics")
    op.drop_table("metrics")
