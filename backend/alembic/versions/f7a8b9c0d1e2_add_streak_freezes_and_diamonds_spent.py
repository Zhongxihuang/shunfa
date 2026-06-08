"""add streak_freezes and diamonds_spent to users (W3 retention + diamond sink)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-08 14:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # streak_freezes: everyone starts with one free protection card.
    op.add_column(
        'users',
        sa.Column(
            'streak_freezes',
            sa.Integer(),
            nullable=False,
            server_default='1',
        ),
    )
    # diamonds_spent: lifetime diamonds spent on redemptions. Backfill 0 so the
    # effective balance (earned − spent) stays unchanged for existing users.
    op.add_column(
        'users',
        sa.Column(
            'diamonds_spent',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'diamonds_spent')
    op.drop_column('users', 'streak_freezes')
