"""add_per_page_billing_fields_to_jobs

Revision ID: 57f94fe88a51
Revises: 47671b90c04b
Create Date: 2026-01-18 15:43:33.322222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57f94fe88a51'
down_revision: Union[str, Sequence[str], None] = '47671b90c04b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-page billing fields to jobs table."""
    op.add_column('jobs', sa.Column('page_count', sa.Integer(), nullable=True, comment='Calculated page count for billing'))
    op.add_column('jobs', sa.Column('credits_charged', sa.Integer(), nullable=False, server_default='0', comment='Credits charged (1 Credit = 1 Page)'))
    op.add_column('jobs', sa.Column('billing_status', sa.String(length=50), nullable=False, server_default='pending', comment='pending, charged, billing_failed, refunded'))


def downgrade() -> None:
    """Remove per-page billing fields from jobs table."""
    op.drop_column('jobs', 'billing_status')
    op.drop_column('jobs', 'credits_charged')
    op.drop_column('jobs', 'page_count')
