"""human_labels, agreement_metrics, label_queue, users; dataset visibility

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-10

M4 surface: human annotation rows, agreement scores per metric@v + project,
active-learning queue, minimal users table for label attribution, and a
visibility flag on datasets so private-by-default + publish picker has a home.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("email", sa.String(length=256), nullable=False, unique=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "human_labels",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "metric_id",
            sa.String(length=26),
            sa.ForeignKey("metrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "metric_version_id",
            sa.String(length=26),
            sa.ForeignKey("metric_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "record_id",
            sa.String(length=26),
            sa.ForeignKey("dataset_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "metric_version_id",
            "record_id",
            "user_id",
            name="uq_human_labels_mv_record_user",
        ),
    )
    op.create_index(
        "ix_human_labels_project_metric",
        "human_labels",
        ["project_id", "metric_id", "created_at"],
    )
    op.create_index(
        "ix_human_labels_metric_version",
        "human_labels",
        ["metric_version_id"],
    )

    op.create_table(
        "agreement_metrics",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "metric_id",
            sa.String(length=26),
            sa.ForeignKey("metrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "metric_version_id",
            sa.String(length=26),
            sa.ForeignKey("metric_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("n_labels", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cohen_kappa", sa.Float, nullable=True),
        sa.Column("fleiss_kappa", sa.Float, nullable=True),
        sa.Column("pearson_r", sa.Float, nullable=True),
        sa.Column("spearman_r", sa.Float, nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "metric_version_id",
            name="uq_agreement_project_metric_version",
        ),
    )
    op.create_index(
        "ix_agreement_metric_id",
        "agreement_metrics",
        ["metric_id", "computed_at"],
    )

    op.create_table(
        "label_queue",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "metric_id",
            sa.String(length=26),
            sa.ForeignKey("metrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "record_id",
            sa.String(length=26),
            sa.ForeignKey("dataset_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Float, nullable=False, server_default="0"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "claimed_by",
            sa.String(length=26),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "metric_id",
            "record_id",
            name="uq_label_queue_project_metric_record",
        ),
    )
    op.create_index(
        "ix_label_queue_priority",
        "label_queue",
        ["project_id", "metric_id", "completed_at", "priority"],
    )

    op.add_column(
        "datasets",
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default="private",
        ),
    )
    op.add_column(
        "datasets",
        sa.Column("license", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("datasets", "license")
    op.drop_column("datasets", "visibility")
    op.drop_index("ix_label_queue_priority", table_name="label_queue")
    op.drop_table("label_queue")
    op.drop_index("ix_agreement_metric_id", table_name="agreement_metrics")
    op.drop_table("agreement_metrics")
    op.drop_index("ix_human_labels_metric_version", table_name="human_labels")
    op.drop_index("ix_human_labels_project_metric", table_name="human_labels")
    op.drop_table("human_labels")
    op.drop_table("users")
