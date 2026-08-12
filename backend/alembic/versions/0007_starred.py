"""starred words

Revision ID: 0007_starred
Revises: 0006_daily_stats
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_starred"
down_revision: Union[str, None] = "0006_daily_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_word_progress",
        sa.Column("starred", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_word_progress", "starred")
