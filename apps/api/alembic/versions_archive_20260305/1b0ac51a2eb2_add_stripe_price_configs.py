"""add_stripe_price_configs

Revision ID: 1b0ac51a2eb2
Revises: b8c3d4e5f6a7
Create Date: 2025-12-02 13:41:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1b0ac51a2eb2'
down_revision: Union[str, Sequence[str], None] = 'b8c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建stripe_price_configs表"""
    op.create_table(
        'stripe_price_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('price_id', sa.String(255), nullable=False, unique=True),
        sa.Column('product_type', sa.String(50), nullable=False),
        sa.Column('plan_id', sa.String(50), nullable=False),
        sa.Column('credits_amount', sa.Integer(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(10), nullable=False, server_default='CNY'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_stripe_price_configs_price_id', 'stripe_price_configs', ['price_id'], unique=True)


def downgrade() -> None:
    """删除stripe_price_configs表"""
    op.drop_index('ix_stripe_price_configs_price_id', table_name='stripe_price_configs')
    op.drop_table('stripe_price_configs')

