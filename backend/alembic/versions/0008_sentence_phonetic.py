"""example sentence phonetic transliteration + generation call kind

Revision ID: 0008_sentence_phonetic
Revises: 0007_starred
Create Date: 2026-08-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_sentence_phonetic"
down_revision: Union[str, None] = "0007_starred"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("word_pairs", sa.Column("example_sentence_phonetic_es", sa.Text(), nullable=True))
    op.add_column(
        "generation_call_log",
        sa.Column("call_kind", sa.String(length=24), nullable=False, server_default="generate"),
    )


def downgrade() -> None:
    op.drop_column("generation_call_log", "call_kind")
    op.drop_column("word_pairs", "example_sentence_phonetic_es")
