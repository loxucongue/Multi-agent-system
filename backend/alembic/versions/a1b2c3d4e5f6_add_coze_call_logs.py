"""add coze_call_logs table

Revision ID: a1b2c3d4e5f6
Revises: 690e8790de0f
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON


revision = "a1b2c3d4e5f6"
down_revision = "690e8790de0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coze_call_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=50), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("call_type", sa.String(length=30), nullable=False),
        sa.Column("workflow_id", sa.String(length=100), nullable=True),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("request_params", JSON(), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_data", JSON(), nullable=True),
        sa.Column("coze_logid", sa.String(length=100), nullable=True),
        sa.Column("debug_url", sa.String(length=500), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coze_call_logs_trace_id", "coze_call_logs", ["trace_id"])
    op.create_index("ix_coze_call_logs_session_id", "coze_call_logs", ["session_id"])
    op.create_index("ix_coze_call_logs_call_type", "coze_call_logs", ["call_type"])
    op.create_index("ix_coze_call_logs_created_at", "coze_call_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_coze_call_logs_created_at", table_name="coze_call_logs")
    op.drop_index("ix_coze_call_logs_call_type", table_name="coze_call_logs")
    op.drop_index("ix_coze_call_logs_session_id", table_name="coze_call_logs")
    op.drop_index("ix_coze_call_logs_trace_id", table_name="coze_call_logs")
    op.drop_table("coze_call_logs")
