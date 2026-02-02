"""convert status to string 20

Revision ID: e8b123456789
Revises: c7af0886d0a3
Create Date: 2026-02-01 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8b123456789'
down_revision: Union[str, Sequence[str], None] = 'c7af0886d0a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert status column to String(20) using explicit cast
    op.alter_column('webhook_secrets', 'status',
               existing_type=postgresql.ENUM('active', 'revoked', 'rotated', name='webhooksecretstatus'),
               type_=sa.String(length=20),
               existing_nullable=False,
               postgresql_using='status::text')
    
    # Drop the Enum type
    sa.Enum(name='webhooksecretstatus').drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Re-create the Enum type
    webhook_status_enum = postgresql.ENUM('active', 'revoked', 'rotated', name='webhooksecretstatus')
    webhook_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Convert status column back to Enum using explicit cast
    op.alter_column('webhook_secrets', 'status',
               existing_type=sa.String(length=20),
               type_=webhook_status_enum,
               existing_nullable=False,
               postgresql_using='status::webhooksecretstatus')
