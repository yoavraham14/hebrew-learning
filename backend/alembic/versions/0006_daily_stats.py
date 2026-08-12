"""daily goal, longest streak, daily activity table

Revision ID: 0006_daily_stats
Revises: 0005_fluency
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_daily_stats"
down_revision: Union[str, None] = "0005_fluency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("daily_goal", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "profiles",
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    # No historical daily data exists to derive a true longest streak from
    # — current_streak is the best known lower bound for existing profiles,
    # so backfill from it rather than leaving everyone at 0 (which would be
    # visibly wrong for anyone already mid-streak).
    op.execute("UPDATE profiles SET longest_streak = current_streak")

    op.create_table(
        "daily_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("profile_id", "activity_date", name="uq_profile_activity_date"),
    )
    op.create_index("ix_daily_activity_profile_id", "daily_activity", ["profile_id"])
    op.create_index("ix_daily_activity_activity_date", "daily_activity", ["activity_date"])


def downgrade() -> None:
    op.drop_index("ix_daily_activity_activity_date", table_name="daily_activity")
    op.drop_index("ix_daily_activity_profile_id", table_name="daily_activity")
    op.drop_table("daily_activity")
    op.drop_column("profiles", "longest_streak")
    op.drop_column("profiles", "daily_goal")
