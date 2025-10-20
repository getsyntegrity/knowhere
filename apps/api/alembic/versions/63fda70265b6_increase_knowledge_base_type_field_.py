"""increase_knowledge_base_type_field_length

Revision ID: 63fda70265b6
Revises: add_state_machine_improvements
Create Date: 2025-10-20 16:38:04.582287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63fda70265b6'
down_revision: Union[str, Sequence[str], None] = 'add_state_machine_improvements'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 增加 knowledge_base 表 type 字段长度从 200 到 1000
    op.alter_column('knowledge_base', 'type',
                   existing_type=sa.VARCHAR(length=200),
                   type_=sa.String(length=1000),
                   existing_comment='内容类型（如PTXT, SUMMARY等）',
                   existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚 knowledge_base 表 type 字段长度从 1000 到 200
    op.alter_column('knowledge_base', 'type',
                   existing_type=sa.String(length=1000),
                   type_=sa.VARCHAR(length=200),
                   existing_comment='内容类型（如PTXT, SUMMARY等）',
                   existing_nullable=True)
