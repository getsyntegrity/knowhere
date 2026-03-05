"""merge_payment_records_and_oauth_providers

Revision ID: 6377dbf9a116
Revises: 23607ad5e16a, c9d8e7f6a5b4
Create Date: 2025-12-02 21:56:06.266199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6377dbf9a116'
down_revision: Union[str, Sequence[str], None] = ('23607ad5e16a', 'c9d8e7f6a5b4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
