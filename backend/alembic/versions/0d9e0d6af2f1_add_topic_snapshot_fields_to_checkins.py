"""add topic snapshot fields to checkins

Revision ID: 0d9e0d6af2f1
Revises: 7f26c8f8a1d1
Create Date: 2026-04-10 19:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0d9e0d6af2f1'
down_revision: Union[str, Sequence[str], None] = '7f26c8f8a1d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('checkins', sa.Column('topic_source', sa.String(), nullable=True))
    op.add_column('checkins', sa.Column('topic_url', sa.Text(), nullable=True))
    op.add_column('checkins', sa.Column('topic_summary', sa.Text(), nullable=True))
    op.add_column('checkins', sa.Column('topic_published_at', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('checkins', 'topic_published_at')
    op.drop_column('checkins', 'topic_summary')
    op.drop_column('checkins', 'topic_url')
    op.drop_column('checkins', 'topic_source')
