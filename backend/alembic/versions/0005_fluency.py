"""fluency threshold + word status

Revision ID: 0005_fluency
Revises: 0004_hebrew_audio
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_fluency"
down_revision: Union[str, None] = "0004_hebrew_audio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("fluency_threshold", sa.Integer(), nullable=False, server_default="3"),
    )

    # server_default="learning" grandfathers every existing progress row —
    # they've all been rated at least once already (a row only exists once
    # a card has been served and rated), so "new" would misrepresent them.
    # New rows explicitly set status at insert time going forward; the
    # Python-side model default of "new" only matters for that path.
    op.add_column(
        "user_word_progress",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="learning"),
    )
    op.add_column(
        "user_word_progress",
        sa.Column("fluent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_word_progress", "fluent_at")
    op.drop_column("user_word_progress", "status")
    op.drop_column("profiles", "fluency_threshold")
