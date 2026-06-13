"""add gamification_override to users (cold-start Appendix A within-subject switch)

Revision ID: 1a2b3c4d5e6f
Revises: f7a8b9c0d1e2
Create Date: 2026-06-08 19:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no server_default: NULL means "use the stable md5 bucket", so all
    # existing rows keep their current behaviour with zero backfill.
    op.add_column(
        'users',
        sa.Column('gamification_override', sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'gamification_override')
