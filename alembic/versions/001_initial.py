"""initial application catalog

Revision ID: 001_initial
Revises:
Create Date: 2026-09-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("cluster_uid", sa.String(length=128), nullable=True),
        sa.Column("namespace", sa.String(length=128), nullable=True),
        sa.Column("k8s_name", sa.String(length=128), nullable=True),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("open_in_new_tab", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("cluster_uid"),
    )
    op.create_table(
        "blocked_identity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cluster_uid", sa.String(length=128), nullable=True),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("k8s_name", sa.String(length=128), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cluster_uid"),
    )


def downgrade() -> None:
    op.drop_table("blocked_identity")
    op.drop_table("application")
