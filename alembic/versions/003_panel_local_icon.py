"""panel local icon copy (icon stored in the database)

Revision ID: 003_panel_local_icon
Revises: 002_panel_value_locks
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_panel_local_icon"
down_revision: Union[str, None] = "002_panel_value_locks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("application") as batch:
        batch.add_column(sa.Column("icon_data", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("icon_mime", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("icon_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("application") as batch:
        batch.drop_column("icon_updated_at")
        batch.drop_column("icon_mime")
        batch.drop_column("icon_data")
