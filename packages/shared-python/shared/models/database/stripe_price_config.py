"""
Stripe价格配置数据模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.database import Base


class StripePriceConfig(Base):
    """Stripe价格配置模型"""
    __tablename__ = "stripe_price_configs"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    price_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)  # subscription/credits_package
    plan_id: Mapped[str] = mapped_column(String(50), nullable=False)  # plus/pro/credits_500等
    credits_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default='0')  # Micro-credits (1 display credit = 1,000,000 micros)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')  # 金额（分，必填，用于验证和前端显示）
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default='CNY')
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('price_id', name='uq_stripe_price_config_price_id'),
    )
    
    def __repr__(self):
        return f"<StripePriceConfig(id={self.id}, price_id='{self.price_id}', product_type='{self.product_type}', plan_id='{self.plan_id}')>"
    
    def is_subscription(self) -> bool:
        """检查是否为订阅类型"""
        return self.product_type == 'subscription'
    
    def is_credits_package(self) -> bool:
        """检查是否为Credits包类型"""
        return self.product_type == 'credits_package'

