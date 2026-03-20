"""add route cover image

Revision ID: a7b8c9d0e1f2
Revises: f6g7h8i9j0k1
Create Date: 2026-03-19 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6g7h8i9j0k1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cover_image column to routes table."""

    op.add_column("routes", sa.Column("cover_image", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Drop cover_image column from routes table."""

    op.drop_column("routes", "cover_image")
