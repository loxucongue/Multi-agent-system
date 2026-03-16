"""convert route parse text fields to json

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "f6g7h8i9j0k1"
down_revision = "e5f6g7h8i9j0"
branch_labels = None
depends_on = None


JSON_ARRAY_COLUMNS = ("highlights", "notice", "included", "cost_excluded")
JSON_OBJECT_COLUMNS = ("base_info",)


def _is_json_type(column_type: object) -> bool:
    return "JSON" in type(column_type).__name__.upper()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("routes")}

    for column_name in JSON_ARRAY_COLUMNS:
        bind.execute(sa.text(f"UPDATE routes SET {column_name} = '[]'"))

    for column_name in JSON_OBJECT_COLUMNS:
        bind.execute(sa.text(f"UPDATE routes SET {column_name} = '{{}}'"))

    for column_name in JSON_ARRAY_COLUMNS:
        column = columns.get(column_name)
        if column and not _is_json_type(column["type"]):
            op.alter_column(
                "routes",
                column_name,
                existing_type=sa.Text(),
                type_=mysql.JSON(),
                existing_nullable=False,
            )

    for column_name in JSON_OBJECT_COLUMNS:
        column = columns.get(column_name)
        if column and not _is_json_type(column["type"]):
            op.alter_column(
                "routes",
                column_name,
                existing_type=sa.Text(),
                type_=mysql.JSON(),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("routes")}

    for column_name in (*JSON_ARRAY_COLUMNS, *JSON_OBJECT_COLUMNS):
        column = columns.get(column_name)
        if column and _is_json_type(column["type"]):
            op.alter_column(
                "routes",
                column_name,
                existing_type=mysql.JSON(),
                type_=sa.Text(),
                existing_nullable=False,
            )
