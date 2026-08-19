"""word_pairs.sentence_source — per-row sentence provenance tracking

Revision ID: 0011_sentence_source
Revises: 0010_sentence_rules_version
Create Date: 2026-08-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_sentence_source"
down_revision: Union[str, None] = "0010_sentence_rules_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="generated" grandfathers every existing row — correct,
    # since every row that exists today was in fact produced by fresh
    # generation, not a backfill pass of either kind.
    op.add_column(
        "word_pairs", sa.Column("sentence_source", sa.String(length=16), nullable=False, server_default="generated")
    )


def downgrade() -> None:
    op.drop_column("word_pairs", "sentence_source")
