"""key api key hashes

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-01 05:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE api_keys SET is_active = false")
    op.add_column(
        "api_keys",
        sa.Column("hash_version", sa.String(length=16), nullable=False, server_default="hmac-v1"),
    )
    op.alter_column("api_keys", "hash_version", server_default=None)


def downgrade() -> None:
    op.drop_column("api_keys", "hash_version")
