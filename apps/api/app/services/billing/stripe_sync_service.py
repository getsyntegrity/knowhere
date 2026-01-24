"""
Stripe价格同步服务
用于从Stripe API获取价格信息并更新数据库
"""
from shared.core.billing import MicroDollar
from typing import Optional
import stripe
from shared.core.config import settings
from shared.core.logging import logger
from app.repositories.stripe_price_config_repository import StripePriceConfigRepository
from sqlalchemy.ext.asyncio import AsyncSession


class StripeSyncService:
    """Stripe价格同步服务"""
    
    def __init__(self):
        self.repository = StripePriceConfigRepository()
    
    async def sync_price_from_stripe(self, db: AsyncSession, price_id: str) -> bool:
        """
        从Stripe API获取价格信息并更新数据库
        
        Args:
            db: 数据库会话
            price_id: Stripe Price ID
            
        Returns:
            bool: 是否同步成功
        """
        try:
            # 从数据库获取配置
            config = await self.repository.get_by_price_id(db, price_id)
            if not config:
                logger.error(f"未找到价格配置: {price_id}")
                return False
            
            # 从Stripe获取价格信息
            stripe_price = stripe.Price.retrieve(price_id)
            
            # 更新数据库中的价格信息
            config.amount_cents = stripe_price.unit_amount or 0
            config.currency = stripe_price.currency.upper()
            
            # 如果是credits_package类型，尝试从metadata获取credits_amount
            if config.is_credits_package() and stripe_price.metadata:
                credits_str = stripe_price.metadata.get('credits_amount')
                if credits_str:
                    try:
                        config.credits_amount = MicroDollar.from_dollars(int(credits_str))
                    except ValueError:
                        logger.warning(f"无法解析credits_amount: {credits_str}")
            
            await db.commit()
            await db.refresh(config)
            
            logger.info(f"成功同步价格信息: price_id={price_id}, amount_cents={config.amount_cents}")
            return True
            
        except stripe.StripeError as e:
            logger.error(f"从Stripe获取价格信息失败: {e}")
            return False
        except Exception as e:
            logger.error(f"同步价格信息失败: {e}", exc_info=True)
            await db.rollback()
            return False
    
    async def sync_all_prices_from_stripe(self, db: AsyncSession) -> dict:
        """
        同步所有价格配置的Stripe信息
        
        Returns:
            dict: 同步结果统计
        """
        configs = await self.repository.get_all_active(db)
        results = {
            'total': len(configs),
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        for config in configs:
            success = await self.sync_price_from_stripe(db, config.price_id)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({
                    'price_id': config.price_id,
                    'plan_id': config.plan_id
                })
        
        logger.info(f"价格同步完成: 总计={results['total']}, 成功={results['success']}, 失败={results['failed']}")
        return results

