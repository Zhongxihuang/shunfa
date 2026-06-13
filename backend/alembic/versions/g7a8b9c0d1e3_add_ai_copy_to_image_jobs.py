"""add ai_copy to image_jobs (paste-to-cards AI title + tags)

Revision ID: g7a8b9c0d1e3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-12 12:00:00.000000

The image_jobs flow now also generates AI Xiaohongshu-style title + tags on
top of the deterministic pagination. The result is stored as JSON in a new
`ai_copy` TEXT column so we can re-render the image job without re-paying
the LLM cost, and so get_image_job can return the same title/tags the user
saw at create time.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "g7a8b9c0d1e3"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "image_jobs",
        sa.Column("ai_copy", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("image_jobs", "ai_copy")
