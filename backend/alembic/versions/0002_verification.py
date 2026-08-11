"""translation verification pipeline

Revision ID: 0002_verification
Revises: 0001_initial
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_verification"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default=true grandfathers every existing word_pairs row as
    # verified — they predate this feature and there's no reason to hide
    # them. New rows always set `verified` explicitly at insert time
    # (app/services/word_generator.py), so the Python-side model default of
    # False only matters for that explicit path, never for this backfill.
    op.add_column(
        "word_pairs",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("word_pairs", sa.Column("verification_note", sa.Text(), nullable=True))

    op.add_column(
        "generation_call_log",
        sa.Column("api_calls_made", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "generation_call_log", sa.Column("verify_status", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "generation_call_log",
        sa.Column("words_verified_ok", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("generation_call_log", "words_verified_ok")
    op.drop_column("generation_call_log", "verify_status")
    op.drop_column("generation_call_log", "api_calls_made")
    op.drop_column("word_pairs", "verification_note")
    op.drop_column("word_pairs", "verified")
