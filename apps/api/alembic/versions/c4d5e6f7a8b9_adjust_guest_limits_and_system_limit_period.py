"""Adjust guest limits and add system limit period support.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-06 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUEST_ROUTE_METHOD: str = "POST"
_GUEST_ROUTE_PATTERN: str = "/v1/guest"
_DEFAULT_PERIOD: str = "minute"
_GUEST_PERIOD: str = "day"
_GUEST_DAILY_LIMIT: int = 100
_GUEST_HOURLY_LIMIT: int = 50
_GUEST_TIER_NAME: str = "guest"
_GUEST_MAX_CONCURRENT_JOBS: int = 10
_GUEST_RPM_LIMIT: int = 20
_GUEST_DAILY_QUOTA: int = -1


def upgrade() -> None:
    """Add rate-limit periods and tighten guest throughput defaults."""
    op.add_column(
        "system_limits",
        sa.Column(
            "period",
            sa.String(length=10),
            nullable=False,
            server_default=_DEFAULT_PERIOD,
        ),
    )
    op.execute(
        """
        UPDATE tier_limits
        SET max_concurrent_jobs = 10,
            rpm_limit = 20,
            daily_quota = -1
        WHERE tier_name = 'guest'
        """
    )
    op.execute(
        """
        UPDATE system_limits
        SET rpm = 100,
            period = 'day',
            description = 'Guest registration endpoint IP rate limit (per day)'
        WHERE method = 'POST' AND api_pattern = '/v1/guest'
        """
    )
    op.alter_column("system_limits", "period", server_default=None)


def downgrade() -> None:
    """Remove rate-limit periods and restore prior guest defaults."""
    op.execute(
        """
        UPDATE tier_limits
        SET max_concurrent_jobs = 10,
            rpm_limit = -1,
            daily_quota = -1
        WHERE tier_name = 'guest'
        """
    )
    op.execute(
        """
        UPDATE system_limits
        SET rpm = 50,
            description = 'Guest registration endpoint IP rate limit (per hour)'
        WHERE method = 'POST' AND api_pattern = '/v1/guest'
        """
    )
    op.drop_column("system_limits", "period")
