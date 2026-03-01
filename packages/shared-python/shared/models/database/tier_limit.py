"""
Tier Limit data model
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.database import Base


class TierLimit(Base):
    """Tier limit model - defines rate limits and quotas per user tier"""
    __tablename__ = "tier_limits"

    tier_name: Mapped[str] = mapped_column(String(20), primary_key=True)
    min_lifetime_amount_micro: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_concurrent_jobs: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = unlimited
    rpm_limit: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = unlimited
    daily_quota: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = unlimited
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<TierLimit(tier_name='{self.tier_name}', display_name='{self.display_name}')>"
