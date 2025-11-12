"""
订阅数据访问层
"""
from typing import List, Optional

from shared.models.database.subscription import Subscription
from app.repositories.base_repository import BaseRepository
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class SubscriptionRepository(BaseRepository[Subscription, dict, dict]):
    """订阅数据访问"""
    
    def __init__(self):
        super().__init__(Subscription)
    
    async def get_by_user_id(self, session: AsyncSession, user_id: str) -> List[Subscription]:
        """获取用户的所有订阅"""
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_active_by_user_id(self, session: AsyncSession, user_id: str) -> Optional[Subscription]:
        """获取用户的活跃订阅"""
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == "active")
            .order_by(Subscription.created_at.desc())
        )
        return result.scalar_one_or_none()
    
    async def get_by_stripe_subscription_id(self, session: AsyncSession, stripe_subscription_id: str) -> Optional[Subscription]:
        """根据Stripe订阅ID获取订阅"""
        result = await session.execute(
            select(Subscription)
            .where(Subscription.stripe_subscription_id == stripe_subscription_id)
        )
        return result.scalar_one_or_none()
    
    async def update_status(self, session: AsyncSession, subscription_id: str, status: str) -> bool:
        """更新订阅状态"""
        from datetime import datetime
        result = await session.execute(
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(status=status, updated_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount > 0
    
    async def cancel_subscription(self, session: AsyncSession, subscription_id: str) -> bool:
        """取消订阅"""
        from datetime import datetime
        result = await session.execute(
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(status="canceled", updated_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount > 0
    
    async def get_by_plan_type(self, session: AsyncSession, plan_type: str) -> List[Subscription]:
        """根据计划类型获取订阅"""
        result = await session.execute(
            select(Subscription)
            .where(Subscription.plan_type == plan_type)
            .where(Subscription.status == "active")
        )
        return result.scalars().all()
