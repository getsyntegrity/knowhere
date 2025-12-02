"""add_payment_records

Revision ID: 23607ad5e16a
Revises: 1b0ac51a2eb2
Create Date: 2025-12-02 13:41:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '23607ad5e16a'
down_revision: Union[str, Sequence[str], None] = '1b0ac51a2eb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建payment_records表"""
    op.create_table(
        'payment_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payment_intent_id', sa.String(255), nullable=True, unique=True),
        sa.Column('checkout_session_id', sa.String(255), nullable=True, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('payment_type', sa.String(50), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='CNY'),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('credits_amount', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.String(50), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_payment_records_payment_intent_id', 'payment_records', ['payment_intent_id'], unique=True)
    op.create_index('ix_payment_records_checkout_session_id', 'payment_records', ['checkout_session_id'], unique=True)
    op.create_index('ix_payment_records_stripe_subscription_id', 'payment_records', ['stripe_subscription_id'])


def downgrade() -> None:
    """删除payment_records表"""
    op.drop_index('ix_payment_records_stripe_subscription_id', table_name='payment_records')
    op.drop_index('ix_payment_records_checkout_session_id', table_name='payment_records')
    op.drop_index('ix_payment_records_payment_intent_id', table_name='payment_records')
    op.drop_table('payment_records')

