"""video library: videos, watched_videos, weekly_video_goal

Revision ID: 0009_video_library
Revises: 0008_sentence_phonetic
Create Date: 2026-08-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_video_library"
down_revision: Union[str, None] = "0008_sentence_phonetic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False),
        sa.UniqueConstraint("youtube_video_id", name="uq_video_youtube_id"),
    )
    op.create_index("ix_videos_ordering", "videos", ["ordering"])

    op.create_table(
        "watched_videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id", sa.Integer(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("watched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "video_id", name="uq_profile_video"),
    )
    op.create_index("ix_watched_videos_profile_id", "watched_videos", ["profile_id"])
    op.create_index("ix_watched_videos_video_id", "watched_videos", ["video_id"])
    op.create_index("ix_watched_videos_watched_at", "watched_videos", ["watched_at"])

    op.add_column("profiles", sa.Column("weekly_video_goal", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("profiles", "weekly_video_goal")
    op.drop_table("watched_videos")
    op.drop_table("videos")
