"""add audit log span and degrade columns

Revision ID: c3d4e5f6g7h
Revises: b2c3d4e5f6g7
Create Date: 2026-03-11 16:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6g7h"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audit_logs")}

    if "parent_span_id" not in columns:
        op.add_column(
            "audit_logs",
            sa.Column(
                "parent_span_id",
                sa.String(length=50),
                nullable=True,
                comment="Parent span for tree structure",
            ),
        )

    if "span_type" not in columns:
        op.add_column(
            "audit_logs",
            sa.Column(
                "span_type",
                sa.String(length=30),
                nullable=True,
                comment="root|node|llm_call|coze_call",
            ),
        )

    if "prompt_version_id" not in columns:
        op.add_column(
            "audit_logs",
            sa.Column(
                "prompt_version_id",
                sa.Integer(),
                nullable=True,
                comment="Prompt version used for A/B tracking",
            ),
        )

    if "is_degraded" not in columns:
        op.add_column(
            "audit_logs",
            sa.Column(
                "is_degraded",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Whether this request used degraded/fallback path",
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audit_logs")}

    if "is_degraded" in columns:
        op.drop_column("audit_logs", "is_degraded")
    if "prompt_version_id" in columns:
        op.drop_column("audit_logs", "prompt_version_id")
    if "span_type" in columns:
        op.drop_column("audit_logs", "span_type")
    if "parent_span_id" in columns:
        op.drop_column("audit_logs", "parent_span_id")