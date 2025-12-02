"""
Stripe价格配置数据访问层
"""
from typing import List, Optional

from shared.models.database.stripe_price_config import StripePriceConfig
from app.repositories.base_repository import BaseRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class StripePriceConfigRepository(BaseRepository[StripePriceConfig, dict, dict]):
    """Stripe价格配置数据访问"""
    
    def __init__(self):
        super().__init__(StripePriceConfig)
    
    async def get_by_price_id(self, session: AsyncSession, price_id: str) -> Optional[StripePriceConfig]:
        """根据价格ID获取配置"""
        result = await session.execute(
            select(StripePriceConfig)
            .where(StripePriceConfig.price_id == price_id)
            .where(StripePriceConfig.is_active == True)
        )
        return result.scalar_one_or_none()
    
    async def get_by_plan_id(self, session: AsyncSession, plan_id: str) -> Optional[StripePriceConfig]:
        """根据计划ID获取配置（订阅类型）"""
        result = await session.execute(
            select(StripePriceConfig)
            .where(StripePriceConfig.plan_id == plan_id)
            .where(StripePriceConfig.product_type == 'subscription')
            .where(StripePriceConfig.is_active == True)
        )
        return result.scalar_one_or_none()
    
    async def get_all_active(self, session: AsyncSession) -> List[StripePriceConfig]:
        """获取所有启用的价格配置"""
        result = await session.execute(
            select(StripePriceConfig)
            .where(StripePriceConfig.is_active == True)
            .order_by(StripePriceConfig.product_type, StripePriceConfig.plan_id)
        )
        return result.scalars().all()
    
    async def get_credits_packages(self, session: AsyncSession) -> List[StripePriceConfig]:
        """获取所有Credits包配置"""
        result = await session.execute(
            select(StripePriceConfig)
            .where(StripePriceConfig.product_type == 'credits_package')
            .where(StripePriceConfig.is_active == True)
            .order_by(StripePriceConfig.credits_amount)
        )
        return result.scalars().all()

