"""add hot topics table

Revision ID: 7f26c8f8a1d1
Revises: b2b8f40c9d1a
Create Date: 2026-04-10 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7f26c8f8a1d1'
down_revision: Union[str, Sequence[str], None] = 'b2b8f40c9d1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hot_topics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic_date', sa.Date(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('published_at', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('ai_angle', sa.Text(), nullable=True),
        sa.Column('ai_counter_angle', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic_date', 'title', name='uq_hot_topics_date_title'),
    )
    op.create_index(op.f('ix_hot_topics_id'), 'hot_topics', ['id'], unique=False)
    op.create_index(op.f('ix_hot_topics_topic_date'), 'hot_topics', ['topic_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hot_topics_topic_date'), table_name='hot_topics')
    op.drop_index(op.f('ix_hot_topics_id'), table_name='hot_topics')
    op.drop_table('hot_topics')
