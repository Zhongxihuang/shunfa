"""add content feedback fields to checkins

Revision ID: b2b8f40c9d1a
Revises: f4ce3438c218
Create Date: 2026-04-10 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2b8f40c9d1a'
down_revision: Union[str, Sequence[str], None] = 'f4ce3438c218'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('checkins', sa.Column('content_feedback', sa.String(), nullable=True))
    op.add_column('checkins', sa.Column('content_feedback_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('checkins', 'content_feedback_at')
    op.drop_column('checkins', 'content_feedback')
