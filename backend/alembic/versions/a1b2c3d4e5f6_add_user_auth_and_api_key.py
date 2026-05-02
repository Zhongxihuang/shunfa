"""add username, password_hash, deepseek_api_key to users

Revision ID: a1b2c3d4e5f6
Revises: 9999999abcde
Create Date: 2026-05-02

"""
from typing import Union, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9999999abcde'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('username', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('password_hash', sa.String(256), nullable=True))
        batch_op.add_column(sa.Column('deepseek_api_key', sa.String(512), nullable=True))
    # Add unique index for username (only on non-null values)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_username', table_name='users')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('deepseek_api_key')
        batch_op.drop_column('password_hash')
        batch_op.drop_column('username')
