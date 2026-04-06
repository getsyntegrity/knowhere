"""Add guest registration: guest_devices table, guest tier, and system limit

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-04 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add guest registration support."""
    # 1. Create guest_devices table
    op.create_table(
        "guest_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("api_key_id", sa.String(36), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("linked_user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_guest_devices_device_id", "guest_devices", ["device_id"], unique=True)
    op.create_index("ix_guest_devices_user_id", "guest_devices", ["user_id"])

    # 2. Insert guest tier into tier_limits
    # Use min_lifetime_amount_micro = -1 so that refresh_tier() (which picks
    # the highest tier where total_spend >= threshold) never accidentally
    # assigns normal users to the guest tier.  Guest users are assigned to
    # this tier explicitly during registration.
    op.execute(
        """
        INSERT INTO tier_limits (tier_name, min_lifetime_amount_micro, max_concurrent_jobs, rpm_limit, daily_quota, display_name)
        VALUES ('guest', -1, 10, -1, -1, 'Guest')
        ON CONFLICT (tier_name) DO NOTHING
        """
    )

    # 3. Insert system limit for guest registration endpoint (50 per hour per IP)
    op.execute(
        """
        INSERT INTO system_limits (method, api_pattern, priority, rpm, description)
        VALUES ('POST', '/v1/guest', 100, 50, 'Guest registration endpoint IP rate limit (per hour)')
        ON CONFLICT (method, api_pattern) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove guest registration support."""
    op.execute("DELETE FROM system_limits WHERE method = 'POST' AND api_pattern = '/v1/guest'")
    op.execute("DELETE FROM tier_limits WHERE tier_name = 'guest'")
    op.drop_index("ix_guest_devices_user_id", table_name="guest_devices")
    op.drop_index("ix_guest_devices_device_id", table_name="guest_devices")
    op.drop_table("guest_devices")
