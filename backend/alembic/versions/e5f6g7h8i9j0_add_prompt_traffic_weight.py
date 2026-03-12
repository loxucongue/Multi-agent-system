"""add traffic_weight to prompt_versions

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6g7h8i9j0"
down_revision = "d4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("prompt_versions")}

    if "traffic_weight" not in columns:
        op.add_column(
            "prompt_versions",
            sa.Column(
                "traffic_weight",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("100"),
                comment="A/B test traffic weight 0-100",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("prompt_versions")}

    if "traffic_weight" in columns:
        op.drop_column("prompt_versions", "traffic_weight")
