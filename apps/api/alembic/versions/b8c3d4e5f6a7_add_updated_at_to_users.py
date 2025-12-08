"""add_updated_at_to_users

Revision ID: b8c3d4e5f6a7
Revises: 7477484d4936
Create Date: 2025-12-02 20:27:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '7477484d4936'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade() -> None:
    """添加 updated_at 列到 users 表"""
    # 检查 users 表是否存在且 updated_at 列不存在
    if not column_exists('users', 'updated_at'):
        op.add_column('users', 
            sa.Column('updated_at', sa.DateTime(), nullable=True)
        )
        # 为现有记录设置默认值
        op.execute("UPDATE users SET updated_at = create_time WHERE updated_at IS NULL")
        # 设置默认值和更新触发器（可选，如果需要自动更新）


def downgrade() -> None:
    """移除 updated_at 列"""
    if column_exists('users', 'updated_at'):
        op.drop_column('users', 'updated_at')

