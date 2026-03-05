"""migrate_credits_columns_to_bigint

Revision ID: b2c3d4e5f6a8
Revises: 57f94fe88a51
Create Date: 2026-01-20 22:55:00.000000

Migrates credit-related columns from Integer to BigInteger for micro-dollar precision.
$1.00 = 1,000,000 micro-credits

Affected columns (all store micro-credits):
- users.credits_balance
- credits_transactions.credits_amount
- jobs.credits_charged
- stripe_price_configs.credits_amount
- payment_records.credits_amount

Note: Existing data is preserved as-is. Old credit values now represent micro-credits.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, Sequence[str], None] = '57f94fe88a51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert credit columns from Integer to BigInteger for micro-dollar precision."""
    
    # users.credits_balance: Integer -> BigInteger
    op.alter_column(
        'users',
        'credits_balance',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default='0'
    )
    
    # credits_transactions.credits_amount: Integer -> BigInteger
    op.alter_column(
        'credits_transactions',
        'credits_amount',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False
    )
    
    # jobs.credits_charged: Integer -> BigInteger
    op.alter_column(
        'jobs',
        'credits_charged',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default='0',
        comment='In micro-credits: $1.00 = 1,000,000'
    )
    
    # stripe_price_configs.credits_amount: Integer -> BigInteger
    op.alter_column(
        'stripe_price_configs',
        'credits_amount',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default='0',
        comment='Micro-credits: 1 display credit = 1,000,000 micros'
    )
    
    # payment_records.credits_amount: Integer -> BigInteger (nullable)
    op.alter_column(
        'payment_records',
        'credits_amount',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True
    )


def downgrade() -> None:
    """Revert credit columns from BigInteger to Integer."""
    
    # payment_records.credits_amount: BigInteger -> Integer
    op.alter_column(
        'payment_records',
        'credits_amount',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True
    )
    
    # stripe_price_configs.credits_amount: BigInteger -> Integer
    op.alter_column(
        'stripe_price_configs',
        'credits_amount',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default='0'
    )
    
    # jobs.credits_charged: BigInteger -> Integer
    op.alter_column(
        'jobs',
        'credits_charged',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default='0',
        comment='Credits charged (1 Credit = 1 Page)'
    )
    
    # credits_transactions.credits_amount: BigInteger -> Integer
    op.alter_column(
        'credits_transactions',
        'credits_amount',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False
    )
    
    # users.credits_balance: BigInteger -> Integer
    op.alter_column(
        'users',
        'credits_balance',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default='0'
    )
