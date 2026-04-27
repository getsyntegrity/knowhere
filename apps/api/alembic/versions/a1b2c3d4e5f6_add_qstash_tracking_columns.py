"""Add QStash tracking columns to webhook_events and webhook_logs

Revision ID: a1b2c3d4e5f6
Revises: 8ffba9132ff0
Create Date: 2026-04-01 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "8ffba9132ff0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add QStash message tracking to webhook tables."""
    # Track QStash message ID on the outbox event
    op.add_column(
        "webhook_events",
        sa.Column("qstash_message_id", sa.String(128), nullable=True),
    )

    # Track delivery provider and QStash message ID on each log entry
    op.add_column(
        "webhook_logs",
        sa.Column(
            "delivery_provider",
            sa.String(20),
            nullable=True,
            server_default="self",
        ),
    )
    op.add_column(
        "webhook_logs",
        sa.Column("qstash_message_id", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    """Remove QStash tracking columns."""
    op.drop_column("webhook_logs", "qstash_message_id")
    op.drop_column("webhook_logs", "delivery_provider")
    op.drop_column("webhook_events", "qstash_message_id")
