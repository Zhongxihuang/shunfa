"""add free_quota_used to users (entry-loop free trial)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-08 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default '0' backfills existing rows so the column can be NOT NULL.
    op.add_column(
        'users',
        sa.Column(
            'free_quota_used',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'free_quota_used')
