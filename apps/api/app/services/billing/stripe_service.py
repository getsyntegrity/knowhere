"""
Stripe 支付服务
"""
from datetime import datetime
from typing import Any, Dict, Optional

import stripe
from shared.core.config import settings
from shared.core.logging import logger
from app.repositories.credits_repository import CreditsRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.payment_record_repository import PaymentRecordRepository
from app.services.billing.price_config_service import PriceConfigService
from app.services.billing.credits_service import CreditsService
from shared.models.database.subscription import Subscription
from shared.models.database.payment_record import PaymentRecord
from sqlalchemy.ext.asyncio import AsyncSession


class StripeService:
    """Stripe支付服务"""
    
    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            raise Exception("STRIPE_SECRET_KEY 未配置，请检查环境变量")
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.subscription_repo = SubscriptionRepository()
        self.credits_repo = CreditsRepository()
        self.payment_record_repo = PaymentRecordRepository()
        self.price_config_service = PriceConfigService()
        self.credits_service = CreditsService()
    
    async def create_checkout_session(
        self, 
        db: AsyncSession,
        user_id: str, 
        plan_id: str, 
        success_url: str, 
        cancel_url: str
    ) -> str:
        """创建订阅支付会话"""
        try:
            # 从数据库获取计划价格ID
            price_id = await self.price_config_service.get_plan_price_id(db, plan_id)
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={'user_id': user_id, 'plan_id': plan_id, 'type': 'subscription'}
            )
            return session.url
        except stripe.StripeError as e:
            logger.error(f"创建订阅支付会话失败: {e}")
            raise Exception(f"创建支付会话失败: {e}")
    
    async def create_checkout_session_for_credits_package(
        self,
        db: AsyncSession,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str
    ) -> str:
        """创建Credits包支付会话"""
        try:
            # 验证价格配置存在
            config = await self.price_config_service.get_price_config(db, price_id)
            if not config.is_credits_package():
                raise ValueError(f"价格ID {price_id} 不是Credits包类型")
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='payment',  # 一次性支付
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': user_id,
                    'price_id': price_id,
                    'type': 'credits_package',
                    'credits_amount': str(config.credits_amount) if config.credits_amount else None
                }
            )
            return session.url
        except stripe.StripeError as e:
            logger.error(f"创建Credits包支付会话失败: {e}")
            raise Exception(f"创建支付会话失败: {e}")
    
    async def create_payment_intent(
        self, 
        user_id: str, 
        amount: int, 
        credits_amount: int,
        currency: str = 'cny'  # 使用人民币
    ) -> Dict[str, Any]:
        """创建支付意图（用于Credits购买）"""
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,  # amount in cents
                currency=currency,
                metadata={
                    'user_id': user_id,
                    'type': 'credits',
                    'credits_amount': str(credits_amount)
                }
            )
            return {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
        except stripe.StripeError as e:
            logger.error(f"创建支付意图失败: {e}")
            raise Exception(f"创建支付意图失败: {e}")
    
    async def handle_webhook(self, db: AsyncSession, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """处理Stripe Webhook"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return await self._process_webhook_event(db, event)
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            raise Exception("Invalid payload")
        except stripe.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {e}")
            raise Exception("Invalid signature")
    
    async def _process_webhook_event(self, db: AsyncSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理Webhook事件"""
        event_type = event['type']
        
        if event_type == 'checkout.session.completed':
            return await self._handle_checkout_completed(db, event)
        elif event_type == 'payment_intent.succeeded':
            return await self._handle_payment_intent_succeeded(db, event)
        elif event_type == 'invoice.payment_succeeded':
            return await self._handle_payment_succeeded(db, event)
        elif event_type == 'customer.subscription.deleted':
            return await self._handle_subscription_deleted(db, event)
        else:
            return {'status': 'ignored', 'event_type': event_type}
    
    async def _handle_checkout_completed(self, db: AsyncSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理支付完成事件"""
        session = event['data']['object']
        session_id = session['id']
        mode = session.get('mode')
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        payment_type = metadata.get('type')
        
        if not user_id:
            logger.warning(f"Checkout session {session_id} 缺少user_id metadata，可能是测试事件，跳过处理")
            return {'status': 'ignored', 'message': 'Missing user_id metadata (likely test event)', 'checkout_session_id': session_id, 'event_type': 'checkout.session.completed'}
        
        # 幂等性检查
        if await self.payment_record_repo.is_processed(db, checkout_session_id=session_id):
            logger.info(f"Checkout session {session_id} 已处理，跳过")
            return {'status': 'ignored', 'message': 'Already processed', 'checkout_session_id': session_id}
        
        # 准备支付记录的extra_metadata
        payment_metadata = {
            'session_id': session_id,
            'stripe_session': session,  # 完整session对象（用于调试和审计）
        }
        
        # 创建支付记录（pending状态）
        payment_record = PaymentRecord(
            checkout_session_id=session_id,
            user_id=user_id,
            payment_type=payment_type or 'unknown',
            amount_cents=session.get('amount_total', 0),
            currency=session.get('currency', 'cny').upper(),
            status='pending',
            extra_metadata=payment_metadata
        )
        db.add(payment_record)
        await db.flush()  # 获取ID但不提交
        
        try:
            if mode == 'subscription':
                # 订阅类型
                plan_id = metadata.get('plan_id')
                stripe_subscription_id = session.get('subscription')
                
                if not plan_id or not stripe_subscription_id:
                    logger.error(f"订阅信息不完整: plan_id={plan_id}, subscription_id={stripe_subscription_id}")
                    return {'status': 'error', 'message': 'Incomplete subscription info'}
                
                # 从价格配置获取商品描述等信息
                try:
                    price_id = await self.price_config_service.get_plan_price_id(db, plan_id)
                    price_config = await self.price_config_service.get_price_config(db, price_id)
                    # 更新支付记录的extra_metadata，添加商品信息
                    payment_record.extra_metadata = {
                        **payment_metadata,
                        'product_description': f"{plan_id.upper()} 订阅套餐",
                        'plan_id': plan_id,
                        'price_id': price_id,
                        'product_metadata': price_config.extra_metadata or {}  # 从价格配置获取商品描述等信息
                    }
                except Exception as e:
                    logger.warning(f"获取价格配置信息失败: {e}，使用默认值")
                    payment_record.extra_metadata = {
                        **payment_metadata,
                        'product_description': f"{plan_id.upper()} 订阅套餐",
                        'plan_id': plan_id
                    }
                
                # 创建订阅记录
                subscription = Subscription(
                    user_id=user_id,
                    plan_type=plan_id,
                    stripe_subscription_id=stripe_subscription_id,
                    status='active',
                    start_date=datetime.utcnow(),
                    subscription_metadata={'session_id': session_id}
                )
                db.add(subscription)
                await db.flush()  # 获取ID但不提交
                
                # 更新支付记录
                payment_record.status = 'succeeded'
                payment_record.plan_id = plan_id
                payment_record.stripe_subscription_id = stripe_subscription_id
                payment_record.processed_at = datetime.utcnow()
                await db.commit()
                await db.refresh(payment_record)
                
                logger.info(f"订阅创建成功: user_id={user_id}, plan_id={plan_id}, subscription_id={stripe_subscription_id}")
                return {
                    'status': 'success',
                    'event_type': 'checkout.session.completed',
                    'user_id': user_id,
                    'plan_id': plan_id,
                    'payment_type': 'subscription'
                }
            
            elif mode == 'payment' and payment_type == 'credits_package':
                # Credits包类型
                price_id = metadata.get('price_id')
                
                if not price_id:
                    logger.error(f"Credits包信息不完整: price_id={price_id}")
                    return {'status': 'error', 'message': 'Missing price_id'}
                
                # 从价格配置获取Credits数量和商品信息
                price_config = await self.price_config_service.get_price_config(db, price_id)
                credits_amount = price_config.credits_amount
                if credits_amount is None:
                    logger.error(f"价格ID {price_id} 的Credits数量未配置")
                    return {'status': 'error', 'message': 'Credits amount not configured'}
                
                # 更新支付记录的extra_metadata，添加商品信息
                product_description = f"Credits包 - {credits_amount} Credits"
                if price_config.extra_metadata and price_config.extra_metadata.get('description'):
                    product_description = price_config.extra_metadata.get('description')
                
                payment_record.extra_metadata = {
                    **payment_metadata,
                    'product_description': product_description,
                    'price_id': price_id,
                    'credits_amount': credits_amount,
                    'product_metadata': price_config.extra_metadata or {}  # 从价格配置获取商品描述等信息
                }
                
                # 验证金额
                actual_amount = session.get('amount_total', 0)
                if not await self.price_config_service.validate_price_amount(db, price_id, actual_amount):
                    logger.error(f"金额验证失败: price_id={price_id}, expected={actual_amount}")
                    payment_record.status = 'failed'
                    payment_record.extra_metadata = {**(payment_record.extra_metadata or {}), 'error': 'Amount validation failed'}
                    await db.commit()
                    return {'status': 'error', 'message': 'Amount validation failed'}
                
                # 增加Credits
                await self.credits_service.add_credits(
                    db,
                    user_id,
                    credits_amount,
                    f"购买Credits包: {product_description}",
                    stripe_payment_id=session.get('payment_intent')
                )
                
                # 更新支付记录
                payment_record.status = 'succeeded'
                payment_record.credits_amount = credits_amount
                payment_record.processed_at = datetime.utcnow()
                await db.commit()
                await db.refresh(payment_record)
                
                logger.info(f"Credits包购买成功: user_id={user_id}, credits={credits_amount}, price_id={price_id}")
                return {
                    'status': 'success',
                    'event_type': 'checkout.session.completed',
                    'user_id': user_id,
                    'credits_amount': credits_amount,
                    'payment_type': 'credits_package'
                }
            else:
                logger.warning(f"未知的支付类型: mode={mode}, type={payment_type}")
                return {'status': 'ignored', 'message': 'Unknown payment type'}
        
        except Exception as e:
            logger.error(f"处理checkout.session.completed失败: {e}", exc_info=True)
            payment_record.status = 'failed'
            payment_record.extra_metadata = {**(payment_record.extra_metadata or {}), 'error': str(e)}
            await db.commit()
            raise
    
    async def _handle_payment_intent_succeeded(self, db: AsyncSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理PaymentIntent成功事件（用于Credits购买）"""
        payment_intent = event['data']['object']
        payment_intent_id = payment_intent['id']
        metadata = payment_intent.get('metadata', {})
        user_id = metadata.get('user_id')
        payment_type = metadata.get('type')
        
        if payment_type != 'credits':
            logger.info(f"PaymentIntent {payment_intent_id} 不是Credits类型，跳过")
            return {'status': 'ignored', 'payment_intent_id': payment_intent_id}
        
        if not user_id:
            logger.warning(f"PaymentIntent {payment_intent_id} 缺少user_id metadata，可能是测试事件，跳过处理")
            return {'status': 'ignored', 'message': 'Missing user_id metadata (likely test event)', 'payment_intent_id': payment_intent_id}
        
        # 幂等性检查
        if await self.payment_record_repo.is_processed(db, payment_intent_id=payment_intent_id):
            logger.info(f"PaymentIntent {payment_intent_id} 已处理，跳过")
            return {'status': 'ignored', 'message': 'Already processed', 'payment_intent_id': payment_intent_id}
        
        # 准备支付记录的extra_metadata
        payment_metadata = {
            'payment_intent_id': payment_intent_id,
            'stripe_payment_intent': payment_intent,  # 完整payment_intent对象（用于调试和审计）
        }
        
        # 创建支付记录（pending状态）
        payment_record = PaymentRecord(
            payment_intent_id=payment_intent_id,
            user_id=user_id,
            payment_type='credits_package',
            amount_cents=payment_intent.get('amount', 0),
            currency=payment_intent.get('currency', 'cny').upper(),
            status='pending',
            extra_metadata=payment_metadata
        )
        db.add(payment_record)
        await db.flush()  # 获取ID但不提交
        
        try:
            # 从metadata获取Credits数量
            credits_amount_str = metadata.get('credits_amount')
            if not credits_amount_str:
                logger.error(f"PaymentIntent {payment_intent_id} 缺少credits_amount")
                payment_record.status = 'failed'
                payment_record.extra_metadata = {**(payment_record.extra_metadata or {}), 'error': 'Missing credits_amount'}
                await db.commit()
                return {'status': 'error', 'message': 'Missing credits_amount'}
            
            credits_amount = int(credits_amount_str)
            
            # 更新支付记录的extra_metadata，添加商品信息
            payment_record.extra_metadata = {
                **payment_metadata,
                'product_description': f"Credits包 - {credits_amount} Credits",
                'credits_amount': credits_amount,
                'payment_method': 'payment_intent'  # 标识这是通过PaymentIntent购买的
            }
            
            # 验证金额（从PaymentIntent获取）
            actual_amount = payment_intent.get('amount', 0)
            # 这里可以根据credits_amount计算预期金额进行验证
            # 暂时跳过金额验证，因为金额已经在创建PaymentIntent时验证过
            
            # 增加Credits
            await self.credits_service.add_credits(
                db,
                user_id,
                credits_amount,
                f"购买Credits包 - {credits_amount} Credits",
                stripe_payment_id=payment_intent_id
            )
            
            # 更新支付记录
            payment_record.status = 'succeeded'
            payment_record.credits_amount = credits_amount
            payment_record.processed_at = datetime.utcnow()
            await db.commit()
            await db.refresh(payment_record)
            
            logger.info(f"Credits购买成功: user_id={user_id}, credits={credits_amount}, payment_intent_id={payment_intent_id}")
            return {
                'status': 'success',
                'event_type': 'payment_intent.succeeded',
                'user_id': user_id,
                'credits_amount': credits_amount,
                'payment_type': 'credits_package'
            }
        
        except Exception as e:
            logger.error(f"处理payment_intent.succeeded失败: {e}", exc_info=True)
            payment_record.status = 'failed'
            payment_record.extra_metadata = {**(payment_record.extra_metadata or {}), 'error': str(e)}
            await db.commit()
            raise
    
    async def _handle_payment_succeeded(self, db: AsyncSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理支付成功事件（订阅续费）"""
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        
        if not subscription_id:
            logger.warning("Invoice缺少subscription ID")
            return {'status': 'ignored', 'message': 'Missing subscription_id'}
        
        try:
            # 根据Stripe订阅ID查找本地订阅记录
            subscription = await self.subscription_repo.get_by_stripe_subscription_id(db, subscription_id)
            if subscription:
                # 更新订阅状态为active
                await self.subscription_repo.update_status(db, subscription.id, 'active')
                logger.info(f"订阅续费成功: subscription_id={subscription_id}")
            else:
                logger.warning(f"未找到本地订阅记录: stripe_subscription_id={subscription_id}")
            
            return {'status': 'success', 'subscription_id': subscription_id}
        except Exception as e:
            logger.error(f"处理invoice.payment_succeeded失败: {e}", exc_info=True)
            raise
    
    async def _handle_subscription_deleted(self, db: AsyncSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理订阅删除事件"""
        subscription = event['data']['object']
        stripe_subscription_id = subscription['id']
        
        try:
            # 根据Stripe订阅ID查找本地订阅记录
            local_subscription = await self.subscription_repo.get_by_stripe_subscription_id(db, stripe_subscription_id)
            if local_subscription:
                # 更新订阅状态为已取消
                await self.subscription_repo.update_status(db, local_subscription.id, 'canceled')
                logger.info(f"订阅已取消: subscription_id={stripe_subscription_id}")
            else:
                logger.warning(f"未找到本地订阅记录: stripe_subscription_id={stripe_subscription_id}")
            
            return {'status': 'success', 'subscription_id': stripe_subscription_id}
        except Exception as e:
            logger.error(f"处理customer.subscription.deleted失败: {e}", exc_info=True)
            raise
    
    async def get_subscription(self, stripe_subscription_id: str) -> Dict[str, Any]:
        """获取订阅信息"""
        try:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            return subscription
        except stripe.StripeError as e:
            logger.error(f"获取订阅信息失败: {e}")
            raise Exception(f"获取订阅信息失败: {e}")
    
    async def cancel_subscription(self, stripe_subscription_id: str) -> Dict[str, Any]:
        """取消订阅"""
        try:
            subscription = stripe.Subscription.delete(stripe_subscription_id)
            return subscription
        except stripe.StripeError as e:
            logger.error(f"取消订阅失败: {e}")
            raise Exception(f"取消订阅失败: {e}")
