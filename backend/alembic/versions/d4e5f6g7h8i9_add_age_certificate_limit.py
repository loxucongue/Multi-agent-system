"""add age_limit and certificate_limit to routes

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6g7h8i9"
down_revision = "c3d4e5f6g7h"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("routes")}

    if "age_limit" not in columns:
        op.add_column(
            "routes",
            sa.Column("age_limit", sa.Text(), nullable=True, comment="Age limit description"),
        )
    if "certificate_limit" not in columns:
        op.add_column(
            "routes",
            sa.Column("certificate_limit", sa.Text(), nullable=True, comment="Certificate/document requirements"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("routes")}

    if "certificate_limit" in columns:
        op.drop_column("routes", "certificate_limit")
    if "age_limit" in columns:
        op.drop_column("routes", "age_limit")
