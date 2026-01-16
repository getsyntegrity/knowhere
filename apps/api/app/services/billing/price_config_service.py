"""
Stripe价格配置服务
"""
from typing import Optional

from shared.core.logging import logger
from app.repositories.stripe_price_config_repository import StripePriceConfigRepository
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.DomainExceptions import NotFoundException, ValidationException


class PriceConfigService:
    """价格配置服务"""
    
    def __init__(self):
        self.repository = StripePriceConfigRepository()
    
        config = await self.repository.get_by_price_id(session, price_id)
        if not config:
            raise NotFoundException(
                resource="PriceConfig",
                resource_id=price_id,
                internal_message="Price configuration not found"
            )
        return config
    
        config = await self.repository.get_by_plan_id(session, plan_id)
        if not config:
            raise NotFoundException(
                resource="PlanConfig",
                resource_id=plan_id,
                internal_message="Plan configuration not found"
            )
        return config.price_id
    
    async def get_credits_by_price_id(self, session: AsyncSession, price_id: str) -> int:
        """根据价格ID获取Credits数量"""
        config = await self.get_price_config(session, price_id)
        if not config.is_credits_package():
            raise ValidationException(
                user_message="Invalid price type",
                violations=[{"field": "price_id", "description": f"Price ID {price_id} is not a credits package"}]
            )
        if config.credits_amount <= 0:
            raise ValidationException(
                user_message="Invalid credits configuration",
                violations=[{"field": "price_id", "description": f"Price ID {price_id} has invalid credits amount"}]
            )
        return config.credits_amount
    
    async def validate_price_amount(self, session: AsyncSession, price_id: str, amount_cents: int) -> bool:
        """验证金额是否正确"""
        config = await self.get_price_config(session, price_id)
        if config.amount_cents <= 0:
            logger.warning(f"价格ID {price_id} 的金额未配置或为0，跳过验证")
            return True
        if config.amount_cents != amount_cents:
            logger.error(f"金额不匹配: 配置金额={config.amount_cents}, 实际金额={amount_cents}")
            return False
        return True
    
    async def get_all_credits_packages(self, session: AsyncSession):
        """获取所有Credits包配置"""
        return await self.repository.get_credits_packages(session)

