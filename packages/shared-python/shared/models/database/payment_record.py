"""
支付记录数据模型（用于幂等性保证）
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base

if TYPE_CHECKING:
    from shared.models.database.user import User


class PaymentRecord(Base):
    """支付记录模型（用于幂等性保证）"""
    __tablename__ = "payment_records"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    checkout_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(50), nullable=False)  # subscription/credits_package
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 支付金额（分）
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default='CNY')
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # pending/succeeded/failed
    credits_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Credits数量（仅credits_package类型）
    plan_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 计划ID（仅subscription类型）
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)  # Stripe订阅ID（仅subscription类型）
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 处理时间
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    user: Mapped[User] = relationship("User", lazy="select")
    
    __table_args__ = (
        UniqueConstraint('checkout_session_id', name='uq_payment_record_checkout_session_id'),
    )
    
    def __repr__(self):
        return f"<PaymentRecord(id={self.id}, payment_intent_id='{self.payment_intent_id}', status='{self.status}')>"
    
    def is_subscription(self) -> bool:
        """检查是否为订阅类型"""
        return self.payment_type == 'subscription'
    
    def is_credits_package(self) -> bool:
        """检查是否为Credits包类型"""
        return self.payment_type == 'credits_package'
    
    def is_succeeded(self) -> bool:
        """检查是否已成功处理"""
        return self.status == 'succeeded'

