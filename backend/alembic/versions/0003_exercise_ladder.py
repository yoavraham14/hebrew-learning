"""exercise difficulty ladder + review games

Revision ID: 0003_exercise_ladder
Revises: 0002_verification
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_exercise_ladder"
down_revision: Union[str, None] = "0002_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_word_progress",
        sa.Column("exercise_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_word_progress",
        sa.Column("exercise_level_streak", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column(
        "profiles",
        sa.Column("total_reviews", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "recent_miss",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "word_pair_id",
            sa.Integer(),
            sa.ForeignKey("word_pairs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("missed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recent_miss_profile_id", "recent_miss", ["profile_id"])
    op.create_index("ix_recent_miss_missed_at", "recent_miss", ["missed_at"])


def downgrade() -> None:
    op.drop_index("ix_recent_miss_missed_at", table_name="recent_miss")
    op.drop_index("ix_recent_miss_profile_id", table_name="recent_miss")
    op.drop_table("recent_miss")
    op.drop_column("profiles", "total_reviews")
    op.drop_column("user_word_progress", "exercise_level_streak")
    op.drop_column("user_word_progress", "exercise_level")
