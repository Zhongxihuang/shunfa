"""add reminder deliveries table

Revision ID: 3b5c7f4e2a91
Revises: 0d9e0d6af2f1
Create Date: 2026-04-10 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3b5c7f4e2a91'
down_revision: Union[str, Sequence[str], None] = '0d9e0d6af2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reminder_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('reminder_date', sa.Date(), nullable=False),
        sa.Column('channel', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('response_payload', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'reminder_date', 'channel', name='uq_reminder_delivery_user_date_channel'),
    )
    op.create_index(op.f('ix_reminder_deliveries_id'), 'reminder_deliveries', ['id'], unique=False)
    op.create_index(op.f('ix_reminder_deliveries_reminder_date'), 'reminder_deliveries', ['reminder_date'], unique=False)
    op.create_index(op.f('ix_reminder_deliveries_user_id'), 'reminder_deliveries', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reminder_deliveries_user_id'), table_name='reminder_deliveries')
    op.drop_index(op.f('ix_reminder_deliveries_reminder_date'), table_name='reminder_deliveries')
    op.drop_index(op.f('ix_reminder_deliveries_id'), table_name='reminder_deliveries')
    op.drop_table('reminder_deliveries')
