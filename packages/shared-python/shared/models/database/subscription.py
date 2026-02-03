"""
订阅计划数据模型
"""
from __future__ import annotations

from shared.core.billing import MicroDollar
from shared.core.exceptions.domain_exceptions import UndefinedSubscriptionPlanException

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class Subscription(Base):
    """订阅计划模型"""
    __tablename__ = "subscriptions"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))    # 关联用户
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    plan_type: Mapped[str] = mapped_column(String(50), nullable=False)  # free, plus, pro
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # active, canceled, past_due
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    subscription_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    # 关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    # 关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    
    def __repr__(self):
        return f"<Subscription(id={self.id}, plan_type='{self.plan_type}', status='{self.status}')>"
    
    def is_active(self) -> bool:
        """检查订阅是否激活"""
        return self.status == "active" and (self.end_date is None or self.end_date > datetime.utcnow())
    
    def get_micro_dollar_limit(self) -> int:
        credits_map = {
            "free": MicroDollar.from_dollars(100).amount,
            "plus": MicroDollar.from_dollars(1000).amount,
            "pro": MicroDollar.from_dollars(10000).amount
        }

        if self.plan_type not in credits_map:
            raise UndefinedSubscriptionPlanException(
                internal_message=f"Invalid plan type: {self.plan_type}",
                user_message="Invalid subscription plan type",
            )

        return credits_map.get(self.plan_type)
    
    def get_priority_level(self) -> int:
        """获取优先级级别（用于MQ路由）"""
        priority_map = {
            "free": 1,   # 低优先级
            "plus": 5,   # 中优先级
            "pro": 9     # 高优先级
        }
        return priority_map.get(self.plan_type, 1)