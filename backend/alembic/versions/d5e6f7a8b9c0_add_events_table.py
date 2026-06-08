"""add events table for product analytics

Revision ID: d5e6f7a8b9c0
Revises: a1b2c3d4e5f6
Create Date: 2026-06-06 22:45:00.000000

"""
from typing import Union, Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('props_json', sa.Text(), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_events_id'), 'events', ['id'], unique=False)
    op.create_index(op.f('ix_events_user_id'), 'events', ['user_id'], unique=False)
    op.create_index('ix_events_user_event_ts', 'events', ['user_id', 'event', 'ts'], unique=False)
    op.create_index('ix_events_event_ts', 'events', ['event', 'ts'], unique=False)
    op.create_index('ix_events_ts', 'events', ['ts'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_events_ts', table_name='events')
    op.drop_index('ix_events_event_ts', table_name='events')
    op.drop_index('ix_events_user_event_ts', table_name='events')
    op.drop_index(op.f('ix_events_user_id'), table_name='events')
    op.drop_index(op.f('ix_events_id'), table_name='events')
    op.drop_table('events')
