"""add_token_version_to_users

Revision ID: 9999999abcde
Revises: 3b5c7f4e2a91
Create Date: 2026-04-28 16:55:07.774176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9999999abcde'
down_revision: Union[str, Sequence[str], None] = '3b5c7f4e2a91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add token_version column to users table for JWT revocation support."""
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    """Remove token_version column from users table."""
    op.drop_column("users", "token_version")
