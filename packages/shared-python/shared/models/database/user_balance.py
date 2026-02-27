"""
User Balance data model
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base

if TYPE_CHECKING:
    from shared.models.database.user import User


class UserBalance(Base):
    """User balance model — tracks credits balance and tier membership"""
    __tablename__ = "user_balances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    credits_balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    user_tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", lazy="select")

    def __repr__(self) -> str:
        return f"<UserBalance(id={self.id}, user_id='{self.user_id}', tier='{self.user_tier}')>"
