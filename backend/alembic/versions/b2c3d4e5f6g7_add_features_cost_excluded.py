"""add features and cost_excluded to routes

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("routes")}
    indexes = {index["name"] for index in inspector.get_indexes("routes")}

    if "features" not in columns:
        op.add_column(
            "routes",
            sa.Column("features", sa.Text(), nullable=True, comment="线路特色标签文本"),
        )
    if "cost_excluded" not in columns:
        op.add_column(
            "routes",
            sa.Column("cost_excluded", sa.Text(), nullable=True, comment="费用不含说明"),
        )
    if "uq_routes_doc_url" not in indexes:
        op.create_index("uq_routes_doc_url", "routes", ["doc_url"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("routes")}
    indexes = {index["name"] for index in inspector.get_indexes("routes")}

    if "uq_routes_doc_url" in indexes:
        op.drop_index("uq_routes_doc_url", table_name="routes")
    if "cost_excluded" in columns:
        op.drop_column("routes", "cost_excluded")
    if "features" in columns:
        op.drop_column("routes", "features")
