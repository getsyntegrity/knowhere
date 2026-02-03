"""add missing webhook_secrets indexes

Revision ID: def456ghi789
Revises: abc123def456
Create Date: 2026-02-03 22:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'def456ghi789'
down_revision: Union[str, Sequence[str], None] = 'abc123def456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add missing indexes to webhook_secrets table:
    - idx_webhook_secrets_user_endpoint (composite: user_id, endpoint)
    - idx_webhook_secrets_status (on: status)
    
    The model defines these indexes but they were not created in the original migration.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('webhook_secrets')]

    # Add composite index on user_id and endpoint
    if 'idx_webhook_secrets_user_endpoint' not in existing_indexes:
        op.create_index(
            'idx_webhook_secrets_user_endpoint',
            'webhook_secrets',
            ['user_id', 'endpoint'],
            unique=False
        )
    
    # Add index on status
    if 'idx_webhook_secrets_status' not in existing_indexes:
        op.create_index(
            'idx_webhook_secrets_status',
            'webhook_secrets',
            ['status'],
            unique=False
        )


def downgrade() -> None:
    """Remove the added indexes."""
    op.drop_index('idx_webhook_secrets_status', table_name='webhook_secrets')
    op.drop_index('idx_webhook_secrets_user_endpoint', table_name='webhook_secrets')
