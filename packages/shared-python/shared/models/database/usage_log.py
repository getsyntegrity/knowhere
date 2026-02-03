"""
API Usage Log Data Model
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class UsageLog(Base):
    """API Usage Log Model"""
    __tablename__ = "usage_logs"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    api_key_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=1, nullable=False) # micro dollars
    response_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Milliseconds
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 关系
    # Relationships - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    # Relationships - Use SQLAlchemy 2.0 best practices
    # api_key: Mapped[Optional["APIKey"]] = relationship("APIKey", back_populates="usage_logs")  # Commented out to avoid circular import
    
    def __repr__(self):
        return f"<UsageLog(id={self.id}, endpoint='{self.endpoint}', credits_used={self.credits_used})>"
    
    def is_successful(self) -> bool:
        """Check if request successful"""
        return self.status_code is not None and 200 <= self.status_code < 300
    
    def is_error(self) -> bool:
        """Check if request failed"""
        return self.status_code is not None and self.status_code >= 400
