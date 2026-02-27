"""add_rate_limiter_tables

Revision ID: a3f7c9d1e2b4
Revises: b2c3d4e5f6a8
Create Date: 2026-02-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c9d1e2b4'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_tier column, tier_limits table, and system_limits table with seed data."""
    # 1. Add user_tier column to user_balances
    op.add_column(
        'user_balances',
        sa.Column('user_tier', sa.String(length=20), nullable=False, server_default='free'),
    )

    # 2. Create tier_limits table
    op.create_table(
        'tier_limits',
        sa.Column('tier_name', sa.String(20), primary_key=True),
        sa.Column('min_lifetime_amount_cents', sa.Integer(), nullable=False),
        sa.Column('max_concurrent_jobs', sa.Integer(), nullable=False),
        sa.Column('rpm_limit', sa.Integer(), nullable=False),
        sa.Column('daily_quota', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(50), nullable=False),
    )

    # 3. Create system_limits table
    op.create_table(
        'system_limits',
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('api_pattern', sa.String(200), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('rpm', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint('method', 'api_pattern'),
    )

    # 4. Seed tier_limits data
    op.execute(
        """
        INSERT INTO tier_limits (tier_name, min_lifetime_amount_cents, max_concurrent_jobs, rpm_limit, daily_quota, display_name)
        VALUES
            ('free',   0,      2,  2,   20, 'Free'),
            ('tier_1', 1000,   5,  15,  -1, 'Tier 1'),
            ('tier_2', 5000,   10, 20,  -1, 'Tier 2'),
            ('tier_3', 10000,  20, 50,  -1, 'Tier 3'),
            ('tier_4', 50000,  50, 100, -1, 'Tier 4'),
            ('tier_5', 200000, -1, -1,  -1, 'Tier 5')
        """
    )

    # 5. Seed system_limits data
    op.execute(
        """
        INSERT INTO system_limits (method, api_pattern, priority, rpm, description)
        VALUES
            ('POST', '/v1/jobs',                100,  30,   'Job creation - hard ceiling'),
            ('GET',  '/v1/jobs/*',              200,  200,  'Job queries - prevent polling'),
            ('POST', '/v1/billing/buy-credits*', 300, 10,   'Payment endpoints'),
            ('GET',  '/v1/billing/*',           400,  30,   'Billing queries'),
            ('*',    '/v1/auth/*',              500,  20,   'API key management'),
            ('*',    '/v1/webhooks/*',          600,  20,   'Webhook management'),
            ('*',    '/v1/kb/*',                700,  30,   'Knowledge base'),
            ('*',    '*',                       9999, 1000, 'Default for all unmatched endpoints')
        """
    )


def downgrade() -> None:
    """Remove rate limiter tables and user_tier column."""
    op.drop_table('system_limits')
    op.drop_table('tier_limits')
    op.drop_column('user_balances', 'user_tier')
