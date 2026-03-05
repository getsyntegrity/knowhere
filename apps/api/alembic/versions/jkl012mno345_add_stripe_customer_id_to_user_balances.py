"""add stripe_customer_id to user_balances

Revision ID: jkl012mno345
Revises: ghi789jkl012
Create Date: 2026-02-04 01:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'jkl012mno345'
down_revision: Union[str, Sequence[str], None] = 'ghi789jkl012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stripe_customer_id column to user_balances table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_balances')]
    
    if 'stripe_customer_id' not in columns:
        op.add_column('user_balances', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
        print("Column 'stripe_customer_id' added to 'user_balances'")
    else:
        print("Column 'stripe_customer_id' already exists in 'user_balances', skipping")


def downgrade() -> None:
    """Remove stripe_customer_id column from user_balances table."""
    op.drop_column('user_balances', 'stripe_customer_id')
