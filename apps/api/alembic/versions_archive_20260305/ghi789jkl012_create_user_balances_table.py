"""create user_balances table

Revision ID: ghi789jkl012
Revises: def456ghi789
Create Date: 2026-02-04 00:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ghi789jkl012'
down_revision: Union[str, Sequence[str], None] = 'def456ghi789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_balances table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'user_balances' not in tables:
        op.create_table(
            'user_balances',
            sa.Column('user_id', sa.Text(), nullable=False),
            sa.Column('credits_balance', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('user_id')
        )
        print("Table 'user_balances' created")
    else:
        print("Table 'user_balances' already exists, skipping")


def downgrade() -> None:
    """Drop user_balances table."""
    op.drop_table('user_balances')
