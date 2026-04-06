"""
System Limit data model
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.database import Base


class SystemLimit(Base):
    """System limit model - defines per-endpoint rate limits."""
    __tablename__ = "system_limits"

    method: Mapped[str] = mapped_column(String(10), primary_key=True)
    api_pattern: Mapped[str] = mapped_column(String(200), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    rpm: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = unlimited
    period: Mapped[str] = mapped_column(String(10), nullable=False, default="minute")
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SystemLimit(method='{self.method}', api_pattern='{self.api_pattern}', "
            f"rpm={self.rpm}, period='{self.period}')>"
        )
