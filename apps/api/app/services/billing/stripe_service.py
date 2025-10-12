"""
Stripe 支付服务
"""
import stripe
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.credits_repository import CreditsRepository


class StripeService:
    """Stripe支付服务"""
    
    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            raise Exception("STRIPE_SECRET_KEY 未配置，请检查环境变量")
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.subscription_repo = SubscriptionRepository()
        self.credits_repo = CreditsRepository()
    
    async def create_checkout_session(
        self, 
        user_id: str, 
        plan_id: str, 
        success_url: str, 
        cancel_url: str
    ) -> str:
        """创建支付会话"""
        try:
            # 获取计划价格
            price_id = self._get_plan_price_id(plan_id)
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={'user_id': user_id, 'plan_id': plan_id}
            )
            return session.url
        except stripe.StripeError as e:
            raise Exception(f"创建支付会话失败: {e}")
    
    async def create_payment_intent(
        self, 
        user_id: str, 
        amount: int, 
        currency: str = 'cny'  # 使用人民币
    ) -> Dict[str, Any]:
        """创建支付意图（用于Credits购买）"""
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,  # amount in cents
                currency=currency,
                metadata={'user_id': user_id, 'type': 'credits'}
            )
            return {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
        except stripe.StripeError as e:
            raise Exception(f"创建支付意图失败: {e}")
    
    async def handle_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """处理Stripe Webhook"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return await self._process_webhook_event(event)
        except ValueError:
            raise Exception("Invalid payload")
        except stripe.SignatureVerificationError:
            raise Exception("Invalid signature")
    
    async def _process_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理Webhook事件"""
        event_type = event['type']
        
        if event_type == 'checkout.session.completed':
            return await self._handle_checkout_completed(event)
        elif event_type == 'invoice.payment_succeeded':
            return await self._handle_payment_succeeded(event)
        elif event_type == 'customer.subscription.deleted':
            return await self._handle_subscription_deleted(event)
        else:
            return {'status': 'ignored', 'event_type': event_type}
    
    async def _handle_checkout_completed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理支付完成事件"""
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        plan_id = session['metadata']['plan_id']
        
        # 创建订阅记录
        from app.models.database.subscription import Subscription
        from datetime import datetime
        
        subscription = Subscription(
            user_id=user_id,
            plan_type=plan_id,
            stripe_subscription_id=session['subscription'],
            status='active',
            start_date=datetime.utcnow(),
            metadata={'session_id': session['id']}
        )
        
        # 这里需要数据库会话，实际使用时需要传入
        # await self.subscription_repo.create(session, subscription)
        
        return {'status': 'success', 'user_id': user_id, 'plan_id': plan_id}
    
    async def _handle_payment_succeeded(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理支付成功事件"""
        invoice = event['data']['object']
        subscription_id = invoice['subscription']
        
        # 更新订阅状态
        # await self.subscription_repo.update_status(session, subscription_id, 'active')
        
        return {'status': 'success', 'subscription_id': subscription_id}
    
    async def _handle_subscription_deleted(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理订阅删除事件"""
        subscription = event['data']['object']
        stripe_subscription_id = subscription['id']
        
        # 更新订阅状态为已取消
        # await self.subscription_repo.update_status(session, stripe_subscription_id, 'canceled')
        
        return {'status': 'success', 'subscription_id': stripe_subscription_id}
    
    def _get_plan_price_id(self, plan_id: str) -> str:
        """获取计划价格ID"""
        # 这里应该从配置或数据库获取实际的价格ID
        price_map = {
            "plus": "price_plus_monthly",  # 需要替换为实际的Stripe价格ID
            "pro": "price_pro_monthly"     # 需要替换为实际的Stripe价格ID
        }
        
        if plan_id not in price_map:
            raise ValueError(f"未知的计划ID: {plan_id}")
        
        return price_map[plan_id]
    
    async def get_subscription(self, stripe_subscription_id: str) -> Dict[str, Any]:
        """获取订阅信息"""
        try:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            return subscription
        except stripe.StripeError as e:
            raise Exception(f"获取订阅信息失败: {e}")
    
    async def cancel_subscription(self, stripe_subscription_id: str) -> Dict[str, Any]:
        """取消订阅"""
        try:
            subscription = stripe.Subscription.delete(stripe_subscription_id)
            return subscription
        except stripe.StripeError as e:
            raise Exception(f"取消订阅失败: {e}")
