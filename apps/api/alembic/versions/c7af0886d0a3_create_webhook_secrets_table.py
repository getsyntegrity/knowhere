"""create webhook_secrets table

Revision ID: c7af0886d0a3
Revises: d1e2f3a4b5c6
Create Date: 2026-01-30 14:39:40.929945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7af0886d0a3'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'webhook_secrets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('endpoint', sa.String(), nullable=True),
        sa.Column('secret_encrypted', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('active', 'revoked', 'rotated', name='webhooksecretstatus'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_webhook_secrets_user_id'), 'webhook_secrets', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_webhook_secrets_user_id'), table_name='webhook_secrets')
    op.drop_table('webhook_secrets')
    sa.Enum(name='webhooksecretstatus').drop(op.get_bind(), checkfirst=True)
