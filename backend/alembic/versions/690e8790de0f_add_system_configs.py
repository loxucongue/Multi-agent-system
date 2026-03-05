"""add_system_configs

Revision ID: 690e8790de0f
Revises: 0001_initial
Create Date: 2026-03-05 17:51:38.955735
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '690e8790de0f'
down_revision: Union[str, Sequence[str], None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONFIG_TABLE = sa.table(
    'system_configs',
    sa.column('key', sa.String(length=100)),
    sa.column('value', sa.Text()),
    sa.column('description', sa.String(length=255)),
)


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'system_configs',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )

    op.bulk_insert(
        _CONFIG_TABLE,
        [
            {'key': 'SESSION_CONTEXT_TURNS', 'value': '6', 'description': 'Conversation context turns to retain'},
            {'key': 'COZE_RATE_LIMIT_PER_MINUTE', 'value': '800', 'description': 'Coze request limit per minute'},
            {'key': 'SESSION_TTL_DAYS', 'value': '7', 'description': 'Session expiration days'},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table('system_configs')
