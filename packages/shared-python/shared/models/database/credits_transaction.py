"""
Credits 交易记录数据模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class CreditsTransaction(Base):
    """Credits 交易记录模型"""
    __tablename__ = "credits_transactions"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 正数为增加，负数为扣除
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # purchase, usage, bonus, refund
    stripe_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    transaction_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 关系
    # 关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    user: Mapped[User] = relationship("User", back_populates="credits_transactions", lazy="select")
    
    def __repr__(self):
        return f"<CreditsTransaction(id={self.id}, amount={self.credits_amount}, type='{self.transaction_type}')>"
    
    def is_credit(self) -> bool:
        """检查是否为增加Credits"""
        return self.credits_amount > 0
    
    def is_debit(self) -> bool:
        """检查是否为扣除Credits"""
        return self.credits_amount < 0
