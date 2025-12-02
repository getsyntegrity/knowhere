"""add_oauth_providers_table

Revision ID: c9d8e7f6a5b4
Revises: b8c3d4e5f6a7
Create Date: 2025-12-02 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c9d8e7f6a5b4'
down_revision: Union[str, Sequence[str], None] = 'b8c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def constraint_exists(table_name: str, constraint_name: str) -> bool:
    """检查唯一约束是否存在"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        constraints = [c['name'] for c in inspector.get_unique_constraints(table_name)]
        return constraint_name in constraints
    except Exception:
        return False


def upgrade() -> None:
    """创建oauth_providers表（如果不存在）并添加正确的唯一约束"""
    
    # 创建oauth_providers表（如果不存在）
    if not table_exists('oauth_providers'):
        op.create_table('oauth_providers',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('provider', sa.String(length=50), nullable=False),
            sa.Column('provider_user_id', sa.String(length=255), nullable=False),
            sa.Column('provider_email', sa.String(length=255), nullable=True),
            sa.Column('provider_username', sa.String(length=255), nullable=True),
            sa.Column('access_token', sa.Text(), nullable=True),
            sa.Column('refresh_token', sa.Text(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            # 确保每个用户的每个OAuth类型只有一条记录
            sa.UniqueConstraint('user_id', 'provider', name='uk_user_provider'),
            # 防止同一个第三方账号被多个用户绑定
            sa.UniqueConstraint('provider', 'provider_user_id', name='uk_provider_user_id')
        )
    
    # 如果表已存在，检查并添加缺失的唯一约束
    if table_exists('oauth_providers'):
        # 添加 uk_user_provider 约束（如果不存在）
        if not constraint_exists('oauth_providers', 'uk_user_provider'):
            try:
                op.create_unique_constraint('uk_user_provider', 'oauth_providers', ['user_id', 'provider'])
            except Exception:
                # 如果约束已存在或创建失败，忽略
                pass
        
        # 确保 uk_provider_user_id 约束存在（如果原来的约束名不同）
        if not constraint_exists('oauth_providers', 'uk_provider_user_id'):
            # 检查是否有旧的约束名
            if constraint_exists('oauth_providers', 'uk_provider_user'):
                # 删除旧约束
                op.drop_constraint('uk_provider_user', 'oauth_providers', type_='unique')
            # 创建新约束
            try:
                op.create_unique_constraint('uk_provider_user_id', 'oauth_providers', ['provider', 'provider_user_id'])
            except Exception:
                pass


def downgrade() -> None:
    """移除oauth_providers表"""
    if table_exists('oauth_providers'):
        # 删除约束
        if constraint_exists('oauth_providers', 'uk_user_provider'):
            op.drop_constraint('uk_user_provider', 'oauth_providers', type_='unique')
        if constraint_exists('oauth_providers', 'uk_provider_user_id'):
            op.drop_constraint('uk_provider_user_id', 'oauth_providers', type_='unique')
        # 删除表
        op.drop_table('oauth_providers')

