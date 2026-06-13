"""add generation context to checkins

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("checkins") as batch_op:
        batch_op.add_column(sa.Column("generation_context", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("checkins") as batch_op:
        batch_op.drop_column("generation_context")
