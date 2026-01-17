"""add_error_code_to_jobs

Revision ID: 47671b90c04b
Revises: 9af5b5d6cd7e
Create Date: 2026-01-16 19:08:01.625755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '47671b90c04b'
down_revision: Union[str, Sequence[str], None] = '9af5b5d6cd7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_code column to jobs table."""
    op.add_column('jobs', sa.Column('error_code', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Remove error_code column from jobs table."""
    op.drop_column('jobs', 'error_code')
