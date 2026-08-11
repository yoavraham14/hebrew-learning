"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("native_lang", sa.String(length=8), nullable=False),
        sa.Column("target_lang", sa.String(length=8), nullable=False),
        sa.Column("pin_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity_date", sa.Date(), nullable=True),
    )
    op.create_index("ix_profiles_slug", "profiles", ["slug"], unique=True)

    op.create_table(
        "word_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hebrew_word", sa.String(length=128), nullable=False),
        sa.Column("phonetic_en", sa.String(length=128), nullable=False),
        sa.Column("phonetic_es", sa.String(length=128), nullable=False),
        sa.Column("spanish_word", sa.String(length=128), nullable=False),
        sa.Column("english_word", sa.String(length=128), nullable=False),
        sa.Column("part_of_speech", sa.String(length=32), nullable=False),
        sa.Column("cefr_level", sa.String(length=4), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("example_sentence_he", sa.Text(), nullable=False),
        sa.Column("example_sentence_es", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("hebrew_word", "spanish_word", name="uq_word_pair"),
    )

    op.create_table(
        "user_word_progress",
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
        sa.Column("box", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_result", sa.String(length=16), nullable=True),
        sa.Column("times_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "word_pair_id", name="uq_profile_word"),
    )
    op.create_index("ix_user_word_progress_profile_id", "user_word_progress", ["profile_id"])
    op.create_index("ix_user_word_progress_word_pair_id", "user_word_progress", ["word_pair_id"])

    op.create_table(
        "generation_call_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_size_requested", sa.Integer(), nullable=False),
        sa.Column("words_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_generation_call_log_called_at", "generation_call_log", ["called_at"])

    op.create_table(
        "generation_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("halted_reason", sa.Text(), nullable=True),
        sa.Column("halted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("generation_status")
    op.drop_index("ix_generation_call_log_called_at", table_name="generation_call_log")
    op.drop_table("generation_call_log")
    op.drop_index("ix_user_word_progress_word_pair_id", table_name="user_word_progress")
    op.drop_index("ix_user_word_progress_profile_id", table_name="user_word_progress")
    op.drop_table("user_word_progress")
    op.drop_table("word_pairs")
    op.drop_index("ix_profiles_slug", table_name="profiles")
    op.drop_table("profiles")
