"""word_pairs.sentence_rules_version — backfill re-selection tracking

Revision ID: 0010_sentence_rules_version
Revises: 0009_video_library
Create Date: 2026-08-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_sentence_rules_version"
down_revision: Union[str, None] = "0009_video_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="0" grandfathers every existing row in at version 0 —
    # below CURRENT_SENTENCE_RULES_VERSION (1), so the sentence-backfill
    # pass reconsiders ALL of them, including rows a previous (weaker)
    # version of the specificity rules already populated
    # example_sentence_phonetic_es for. That's deliberate: NULL-ness alone
    # is no longer a reliable "needs backfill" signal now that the rules
    # themselves can tighten out from under an already-populated row.
    op.add_column(
        "word_pairs", sa.Column("sentence_rules_version", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("word_pairs", "sentence_rules_version")
