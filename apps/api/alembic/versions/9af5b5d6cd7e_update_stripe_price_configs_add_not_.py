"""update_stripe_price_configs_add_not_null_constraints

Revision ID: 9af5b5d6cd7e
Revises: 6377dbf9a116
Create Date: 2025-12-02 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9af5b5d6cd7e'
down_revision: Union[str, Sequence[str], None] = '6377dbf9a116'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """更新stripe_price_configs表：添加非空约束"""
    
    # 1. 首先，更新所有 null 值：为所有类型的 amount_cents 设置默认值 0（如果为 null）
    # 注意：这里设置为0，实际价格需要手动设置或使用 sync_stripe_prices.py 脚本从 Stripe 同步
    op.execute("""
        UPDATE stripe_price_configs 
        SET amount_cents = 0 
        WHERE amount_cents IS NULL
    """)
    
    # 2. 为所有类型的 credits_amount 设置默认值 0（如果为 null）
    # subscription 类型可以为 0，credits_package 类型后续需要手动设置或从 Stripe 同步
    op.execute("""
        UPDATE stripe_price_configs 
        SET credits_amount = 0 
        WHERE credits_amount IS NULL
    """)
    
    # 3. 修改 amount_cents 为非空（所有类型都必须有价格，即使是0）
    op.alter_column('stripe_price_configs', 'amount_cents',
                    existing_type=sa.Integer(),
                    nullable=False,
                    server_default='0')
    
    # 4. 修改 credits_amount 为非空（所有类型都必须有值，subscription类型可以为0）
    op.alter_column('stripe_price_configs', 'credits_amount',
                    existing_type=sa.Integer(),
                    nullable=False,
                    server_default='0')
    
    # 5. 添加 CHECK 约束：credits_package 类型必须有 credits_amount > 0
    op.execute("""
        ALTER TABLE stripe_price_configs 
        ADD CONSTRAINT chk_credits_package_has_amount 
        CHECK (
            (product_type = 'credits_package' AND credits_amount > 0) OR 
            (product_type = 'subscription')
        )
    """)
    
    # 6. 添加 CHECK 约束：所有类型都必须有 amount_cents >= 0
    op.execute("""
        ALTER TABLE stripe_price_configs 
        ADD CONSTRAINT chk_amount_cents_non_negative 
        CHECK (amount_cents >= 0)
    """)


def downgrade() -> None:
    """回滚更改"""
    # 删除约束
    op.execute("ALTER TABLE stripe_price_configs DROP CONSTRAINT IF EXISTS chk_credits_package_has_amount")
    op.execute("ALTER TABLE stripe_price_configs DROP CONSTRAINT IF EXISTS chk_amount_cents_non_negative")
    
    # 恢复可空
    op.alter_column('stripe_price_configs', 'amount_cents',
                    existing_type=sa.Integer(),
                    nullable=True,
                    server_default=None)
    
    op.alter_column('stripe_price_configs', 'credits_amount',
                    existing_type=sa.Integer(),
                    nullable=True,
                    server_default=None)
