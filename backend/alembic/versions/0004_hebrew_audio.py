"""hebrew pronunciation audio cache

Revision ID: 0004_hebrew_audio
Revises: 0003_exercise_ladder
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_hebrew_audio"
down_revision: Union[str, None] = "0003_exercise_ladder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("word_pairs", sa.Column("hebrew_audio", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("word_pairs", "hebrew_audio")
