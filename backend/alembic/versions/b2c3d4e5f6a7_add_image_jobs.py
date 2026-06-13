"""add image_jobs table (paste-to-cards feature)

Revision ID: b2c3d4e5f6a7
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-08 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'image_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('template', sa.String(length=8), nullable=False, server_default='a'),
        sa.Column('cover_title', sa.Text(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'status',
            sa.Enum('draft', 'rendered', 'failed', name='imagejobstatus'),
            nullable=False,
            server_default='draft',
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_image_jobs_id', 'image_jobs', ['id'])
    op.create_index('ix_image_jobs_user_id', 'image_jobs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_image_jobs_user_id', table_name='image_jobs')
    op.drop_index('ix_image_jobs_id', table_name='image_jobs')
    op.drop_table('image_jobs')
