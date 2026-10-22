"""panel value locks (Use panel values)

Revision ID: 002_panel_value_locks
Revises: 001_initial
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_panel_value_locks"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("application") as batch:
        batch.add_column(
            sa.Column("name_locked", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("description_locked", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("application") as batch:
        batch.drop_column("description_locked")
        batch.drop_column("name_locked")
