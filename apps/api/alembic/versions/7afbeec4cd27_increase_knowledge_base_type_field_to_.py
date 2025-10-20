"""increase_knowledge_base_type_field_to_2000

Revision ID: 7afbeec4cd27
Revises: 63fda70265b6
Create Date: 2025-10-20 16:53:49.926444

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7afbeec4cd27'
down_revision: Union[str, Sequence[str], None] = '63fda70265b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 增加 knowledge_base 表 type 字段长度从 1000 到 2000
    op.alter_column('knowledge_base', 'type',
                   existing_type=sa.String(length=1000),
                   type_=sa.String(length=2000),
                   existing_comment='内容类型（如PTXT, SUMMARY等）',
                   existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚 knowledge_base 表 type 字段长度从 2000 到 1000
    op.alter_column('knowledge_base', 'type',
                   existing_type=sa.String(length=2000),
                   type_=sa.String(length=1000),
                   existing_comment='内容类型（如PTXT, SUMMARY等）',
                   existing_nullable=True)
