"""
Stripe Price Configuration Service
"""

from app.repositories.stripe_price_config_repository import StripePriceConfigRepository
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.exceptions.domain_exceptions import (
    NotFoundException,
    ValidationException,
)
from shared.core.logging import logger


class PriceConfigService:
    """Price configuration service"""

    def __init__(self):
        self.repository = StripePriceConfigRepository()

    async def get_price_config(self, session: AsyncSession, price_id: str):
        """Get configuration by price ID"""
        config = await self.repository.get_by_price_id(session, price_id)
        if not config:
            raise NotFoundException(
                resource="PriceConfig",
                resource_id=price_id,
                internal_message=f"Price configuration not found: {price_id}",
            )
        return config

    async def get_plan_price_id(self, session: AsyncSession, plan_id: str) -> str:
        """Get price ID by plan ID (subscription type)"""
        config = await self.repository.get_by_plan_id(session, plan_id)
        if not config:
            raise NotFoundException(
                resource="PlanConfig",
                resource_id=plan_id,
                internal_message=f"Plan configuration not found: {plan_id}",
            )
        return config.price_id

    async def get_credits_by_price_id(
        self, session: AsyncSession, price_id: str
    ) -> int:
        """Get credits amount by price ID"""
        config = await self.get_price_config(session, price_id)
        if not config.is_credits_package():
            raise ValidationException(
                user_message=f"Price ID {price_id} is not a credits package type",
                violations=[
                    {"field": "price_id", "description": "Not a credits package"}
                ],
            )
        if config.credits_amount <= 0:
            raise ValidationException(
                user_message=f"Price ID {price_id} has invalid credits amount",
                violations=[
                    {
                        "field": "credits_amount",
                        "description": "Credits amount not configured or invalid",
                    }
                ],
            )
        return config.credits_amount

    async def validate_price_amount(
        self, session: AsyncSession, price_id: str, amount_cents: int
    ) -> bool:
        """Validate if the amount is correct"""
        config = await self.get_price_config(session, price_id)
        if config.amount_cents <= 0:
            logger.warning(
                f"Price ID {price_id} amount is not configured or is 0, skipping validation"
            )
            return True
        if config.amount_cents != amount_cents:
            logger.error(
                f"Amount mismatch: configured={config.amount_cents}, actual={amount_cents}"
            )
            return False
        return True

    async def get_all_credits_packages(self, session: AsyncSession):
        """Get all credits package configurations"""
        return await self.repository.get_credits_packages(session)
