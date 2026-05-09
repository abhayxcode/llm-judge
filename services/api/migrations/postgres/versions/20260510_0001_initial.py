"""initial schema: orgs, projects, api_keys, audit_log

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=26),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("settings", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "slug", name="uq_projects_org_id_slug"),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            sa.String(length=26),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=256), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_log_org_id_created_at", "audit_log", ["org_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_org_id_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_api_keys_project_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_projects_org_id", table_name="projects")
    op.drop_table("projects")
    op.drop_table("orgs")
