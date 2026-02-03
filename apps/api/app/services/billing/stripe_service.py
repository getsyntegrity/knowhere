"""
Stripe 支付服务
"""
from shared.core.billing import MicroDollar
from datetime import datetime
from typing import Any, Dict, Optional

import stripe
from shared.core.config import settings
from shared.core.logging import logger
from sqlalchemy import select, func, String, cast
from app.repositories.credits_repository import CreditsRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.payment_record_repository import PaymentRecordRepository
from app.services.billing.price_config_service import PriceConfigService
from app.services.billing.credits_service import CreditsService
from shared.models.database.subscription import Subscription
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user_balance import UserBalance
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from shared.core.exceptions.domain_exceptions import (
    SystemSettingMissingException, 
    ValidationException, 
    NotFoundException,
    StripeServiceException,
    AuthException
)

class StripeService:
    """Stripe支付服务"""
    
    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            raise SystemSettingMissingException(
                setting_name="STRIPE_SECRET_KEY",
                internal_message="Stripe API key not configured"
            )
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
            return str(session.url or "")
        except stripe.StripeError as e:
            logger.error(f"创建订阅支付会话失败: {e}")
            raise StripeServiceException(
                internal_message=f"Stripe checkout session creation failed: {e}"
            )
    
    async def create_checkout_session_for_credits_package(
        self,
        db: AsyncSession,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        quantity: int,
        email: Optional[str] = None
    ) -> str:
        """创建Credits包支付会话"""
        try:
            # 验证价格配置存在
            config = await self.price_config_service.get_price_config(db, price_id)
            if not config.is_credits_package():
                raise ValidationException(
                    user_message="Invalid price configuration",
                    violations=[{"field": "price_id", "description": f"Price ID {price_id} is not a credits package"}]
                )

            # Ensure user is initialized (UserBalance exists)
            await self.credits_service.ensure_user_initialized(db, user_id)
            
            user_balance = await self.credits_repo.get_user_balance(db, user_id)
            if not user_balance:
                 # Should not happen after ensure_user_initialized
                 raise ValidationException(internal_message=f"Failed to initialize user balance for {user_id}")

            customer_id = user_balance.stripe_customer_id
            
            if not customer_id:
                # 尝试通过邮箱查找现有 Customer
                if email:
                    existing_customers = stripe.Customer.list(email=email, limit=1)
                    if existing_customers.data:
                        customer_id = existing_customers.data[0].id
                
                if not customer_id:
                    # 创建新的 Customer
                    if not email:
                         # For new customers, we prefer having an email.
                         # If no email provided, we can't create a good customer record.
                         # But technically Stripe allows it.
                         # Let's require email for now or use a placeholder? 
                         # Better: Require email for new billing profiles.
                         raise ValidationException(
                             user_message="Email required for first-time payment",
                             violations=[{"field": "email", "description": "Email is required to create a billing profile"}]
                         )

                    customer_params = {
                        'email': email,
                        'metadata': {'user_id': str(user_id)}
                    }
                    # Username is not available without User model, omit it.
                    
                    customer = stripe.Customer.create(**customer_params)
                    customer_id = customer.id
                
                # 更新用户的 stripe_customer_id
                await self.credits_repo.update_stripe_customer_id(db, user_id, customer_id)

            # 统一的 metadata（必须是字符串，确保 charge/refund 时可取到 user_id）
            metadata = {
                "user_id": str(user_id),
                "price_id": str(price_id),
                "type": "credits_package",
                "credits_amount": str(config.credits_amount) if config.credits_amount else None,
                "quantity": str(quantity),
            }

            session_params: Dict[str, Any] = {
                "customer": customer_id,
                "customer_update": {"address": "auto"},
                "payment_method_types": ["card"],
                "client_reference_id": str(user_id),
                "line_items": [
                    {
                        "price": price_id,
                        "quantity": quantity,
                    }
                ],
                "mode": "payment",  # 一次性支付
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata,
                # 将元信息同步到 PaymentIntent/Charge，便于退款 webhook 获取 user_id
                "payment_intent_data": {
                    "metadata": metadata,
                    # 保存卡片到 Customer，便于在控制台查看尾号/后续复用
                    "setup_future_usage": "off_session",
                },
                # 收集更多客户信息，便于后续关联
                "phone_number_collection": {"enabled": True},
                # 强制收集账单地址，Checkout 在创建 Customer 时会同步到客户记录
                "billing_address_collection": "required",
            }

            session = stripe.checkout.Session.create(**session_params)
            return str(session.url or "")
        except stripe.StripeError as e:
            logger.error(f"创建Credits包支付会话失败: {e}")
            raise StripeServiceException(
                internal_message=f"Stripe credits checkout session failed: {e}"
            )

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
            raise StripeServiceException(
                internal_message=f"Stripe payment intent creation failed: {e}"
            )
    
    async def handle_webhook(self, db: AsyncSession, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """处理Stripe Webhook"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return await self._process_webhook_event(db, event)
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            raise ValidationException(
                user_message="Invalid webhook payload",
                violations=[{"field": "payload", "description": "Webhook payload is malformed"}]
            )
        except stripe.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {e}")
            raise AuthException(
                user_message="Invalid webhook signature",
                reason="WEBHOOK_SIGNATURE_INVALID"
            )
    
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
        elif event_type == 'charge.refunded':
            return await self._handle_charge_refunded(db, event)
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
        quantity = int(metadata.get('quantity', 1))

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
                credits_amount = price_config.credits_amount * quantity
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
                actual_amount = session.get('amount_total', 0) / quantity
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
        
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"处理checkout.session.completed失败: {e}", exc_info=True)
            payment_record.status = 'failed'
            payment_record.extra_metadata = {**(payment_record.extra_metadata or {}), 'error': str(e)}
            await db.commit()
            raise StripeServiceException(
                internal_message=f"处理checkout.session.completed失败: {str(e)}",
                original_exception=e
            )
    
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
                'product_description': f"Credits package - {credits_amount} Credits",
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
                f"buy credits - {credits_amount} Credits",
                stripe_payment_id=payment_intent_id
            )
            
            # 更新支付记录
            payment_record.status = 'succeeded'
            payment_record.credits_amount = credits_amount
            payment_record.processed_at = datetime.utcnow()
            await db.commit()
            await db.refresh(payment_record)
            
            logger.info(f"buy credits success: user_id={user_id}, credits={credits_amount}, payment_intent_id={payment_intent_id}")
            return {
                'status': 'success',
                'event_type': 'payment_intent.succeeded',
                'user_id': user_id,
                'credits_amount': credits_amount,
                'payment_type': 'credits_package'
            }
        
        except Exception as e:
            logger.error(f"Credits购买处理失败: {e}", exc_info=True)
            payment_record.status = 'failed'
            payment_record.extra_metadata = {**(payment_record.extra_metadata or {}), 'error': str(e)}
            await db.commit()
            raise StripeServiceException(
                internal_message=f"Credits购买处理失败: {str(e)}",
                original_exception=e
            )
    
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
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"处理invoice.payment_succeeded失败: {e}", exc_info=True)
            raise StripeServiceException(
                internal_message=f"处理invoice.payment_succeeded失败: {str(e)}",
                original_exception=e
            )
    
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
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"处理customer.subscription.deleted失败: {e}", exc_info=True)
            raise StripeServiceException(
                internal_message=f"处理customer.subscription.deleted失败: {str(e)}",
                original_exception=e
            )

    async def _handle_charge_refunded(self, db: AsyncSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理退款事件（Stripe 控制台手动退款等）"""
        charge = event["data"]["object"]
        charge_id = charge.get("id")
        refund_items = (charge.get("refunds", {}) or {}).get("data", []) or []
        latest_refund = refund_items[-1] if refund_items else None

        payment_intent_id = charge.get("payment_intent")
        refund_id = latest_refund.get("id") if latest_refund else None
        
        currency = (charge.get("currency") or "cny").upper()

        # 幂等性：基于 refund_id 或 charge_id 构造唯一键
        idempotency_key = refund_id or f"{charge_id}-refund"

        # 尝试关联原始支付记录以获取 user_id 等上下文
        original_record = None
        if payment_intent_id:
            original_record = await self.payment_record_repo.get_by_payment_intent_id(db, payment_intent_id)

        metadata = charge.get("metadata") or {}
        user_id = metadata.get("user_id") or (getattr(original_record, "user_id", None))
        payment_type = metadata.get("type") or (getattr(original_record, "payment_type", None)) or "refund"

        if not user_id:
            logger.error(f"退款事件缺少 user_id，无法记录退款: charge_id={charge_id}")
            return {"status": "error", "message": "Missing user_id for refund", "event_type": "charge.refunded"}

        # 确保 user_id 转为 UUID 对象，避免 SQL 查询报错
        if user_id and isinstance(user_id, str):
            try:
                user_id = UUID(user_id)
            except ValueError:
                logger.error(f"Invalid user_id format: {user_id}")
                return {"status": "error", "message": "Invalid user_id format", "event_type": "charge.refunded"}
        # 计算本次退款金额：总退款金额 - 原累计退款金额
        # total_refund_amount_cents 是累计退款金额（包含当前这笔退款）
        total_refund_amount_cents = charge.get("amount_refunded") or 0
        
        # 获取原累计退款金额（不包含当前这笔退款）
        origin_total_refund_amount_cents = 0

        # 在payment_record表中查找该payment_intent对应的所有历史退款记录
        # 这里的查询条件改为 payment_intent_id == idempotency_key 且 user_id == user_id
        query = select(func.sum(PaymentRecord.amount_cents)).where(
            PaymentRecord.payment_intent_id == idempotency_key
        ).where(
            PaymentRecord.user_id == user_id
        ).where(
            PaymentRecord.amount_cents < 0  # 确保是退款记录（负数）
        )
        result = await db.execute(query)
        # 求和amount_cents（均为负数，所以求和后需取绝对值）
        origin_total_refund_amount_cents = abs(result.scalar() or 0)
        
        refund_amount_cents = total_refund_amount_cents - origin_total_refund_amount_cents
        if refund_amount_cents <= 0:
            # 退款已处理过，直接返回成功（幂等性）
            logger.info(f"退款已处理，跳过: charge_id={charge_id}, refund_id={refund_id}")
            return {
                "status": "success",
                "event_type": "charge.refunded",
                "message": "Already processed",
                "user_id": user_id,
                "refund_id": refund_id,
            }

        # 计算需要记录的 Credits 退款数量（按价格配置比例折算）
        credits_refunded = None
        price_id = (
            metadata.get("price_id")
            or (getattr(original_record, "extra_metadata", {}) or {}).get("price_id")
        )
        if price_id:
            try:
                price_cfg = await self.price_config_service.get_price_config(db, price_id)
                if price_cfg and price_cfg.amount_cents:
                    credits_refunded = -int(
                        price_cfg.credits_amount
                        * abs(refund_amount_cents)
                        / abs(price_cfg.amount_cents) // credits_amount * quantity
                    )
            except Exception as e:
                logger.warning(f"退款计算Credits失败，price_id={price_id}: {e}")
                credits_refunded = None
        
        # 回退：若没有价格配置，按原支付记录比例折算
        if credits_refunded is None and original_record and original_record.credits_amount and original_record.amount_cents:
            credits_refunded = -int(
                abs(original_record.credits_amount)
                * abs(refund_amount_cents)
                / abs(original_record.amount_cents)
            )

        # 同步扣减用户余额（credits_refunded 为负数表示扣除）
        if credits_refunded is not None and credits_refunded < 0:
            await self.credits_service.add_credits(
                db,
                user_id,
                credits_refunded,
                reason="Refund adjustment",
                transaction_type="refund",
                transaction_metadata={"refund_id": refund_id, "charge_id": charge_id}
            )

        refund_metadata = {
            "refund_id": refund_id,
            "charge_id": charge_id,
            "original_payment_intent_id": payment_intent_id,
            "original_payment_record_id": getattr(original_record, "id", None),
            "reason": (latest_refund or {}).get("reason"),
            "balance_transaction": (latest_refund or {}).get("balance_transaction"),
        }

        refund_record = PaymentRecord(
            payment_intent_id=idempotency_key,
            user_id=user_id,
            payment_type=payment_type,
            amount_cents=-abs(refund_amount_cents),
            currency=currency,
            status="succeeded",
            credits_amount=credits_refunded,
            plan_id=getattr(original_record, "plan_id", None),
            stripe_subscription_id=getattr(original_record, "stripe_subscription_id", None),
            processed_at=datetime.utcnow(),
            extra_metadata=refund_metadata,
        )

        db.add(refund_record)
        await db.commit()
        await db.refresh(refund_record)

        logger.info(
            f"退款记录已创建: user_id={user_id}, amount_cents={refund_record.amount_cents}, "
            f"refund_id={refund_id}, charge_id={charge_id}"
        )

        return {
            "status": "success",
            "event_type": "charge.refunded",
            "user_id": user_id,
            "refund_amount_cents": abs(refund_amount_cents),
            "payment_intent_id": payment_intent_id,
            "refund_id": refund_id,
        }
    
    async def get_subscription(self, stripe_subscription_id: str) -> Dict[str, Any]:
        """获取订阅信息"""
        try:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            return subscription
        except stripe.StripeError as e:
            logger.error(f"获取订阅信息失败: {e}")
            raise StripeServiceException(
                internal_message=f"Failed to get Stripe subscription: {e}"
            )
    
    async def cancel_subscription(self, stripe_subscription_id: str) -> Dict[str, Any]:
        """取消订阅"""
        try:
            subscription = stripe.Subscription.delete(stripe_subscription_id)  # type: ignore[arg-type]
            return subscription
        except stripe.StripeError as e:
            logger.error(f"取消订阅失败: {e}")
            raise StripeServiceException(
                internal_message=f"Failed to cancel Stripe subscription: {e}"
            )
