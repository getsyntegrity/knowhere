"""remove secret from webhook_events

Revision ID: 8dfb2ce5f61d
Revises: c7af0886d0a3
Create Date: 2026-01-30 21:07:22.538625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8dfb2ce5f61d'
down_revision: Union[str, Sequence[str], None] = 'c7af0886d0a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Remove secret from webhook_events
    op.drop_column('webhook_events', 'secret')

    # 2. Fix webhook_secrets user_id type (String -> UUID) and FK
    # The previous migration created this as String(36), but users.id is UUID.
    # We must cast it to UUID to create the Foreign Key.
    
    # Drop old index if exists (it was named ix_webhook_secrets_user_id)
    op.drop_index('ix_webhook_secrets_user_id', table_name='webhook_secrets')

    op.execute('ALTER TABLE webhook_secrets ALTER COLUMN user_id TYPE UUID USING user_id::uuid')
    op.create_foreign_key(None, 'webhook_secrets', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # 3. Create missing indexes
    # Composite index for search by user and endpoint
    op.create_index('idx_webhook_secrets_user_endpoint', 'webhook_secrets', ['user_id', 'endpoint'], unique=False)
    # Index for status lookups
    op.create_index('idx_webhook_secrets_status', 'webhook_secrets', ['status'], unique=False)
    # Re-create user_id index with correct name
    op.create_index('idx_webhook_secrets_user_id', 'webhook_secrets', ['user_id'], unique=False)


def downgrade() -> None:
    # 1. Revert webhook_secrets user_id type and FK
    op.drop_constraint(None, 'webhook_secrets', type_='foreignkey')
    op.execute('ALTER TABLE webhook_secrets ALTER COLUMN user_id TYPE VARCHAR(36)')

    # 2. Restore secret to webhook_events
    # We add a default value to handle existing rows, then drop the default if desired
    op.add_column('webhook_events', sa.Column('secret', sa.TEXT(), server_default='', nullable=False))
    op.alter_column('webhook_events', 'secret', server_default=None)

    # 3. Revert indexes
    op.drop_index('idx_webhook_secrets_user_id', table_name='webhook_secrets')
    op.drop_index('idx_webhook_secrets_status', table_name='webhook_secrets')
    op.drop_index('idx_webhook_secrets_user_endpoint', table_name='webhook_secrets')
    op.create_index('ix_webhook_secrets_user_id', 'webhook_secrets', ['user_id'], unique=False)
