"""
计费相关 API
"""

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel
from shared.core.database import get_db
from shared.core.config import settings
from app.core.dependencies import get_current_user
from shared.models.database.user import User
from shared.models.schemas.billing import (BuyCreditsRequest,
                                        CheckoutSessionResponse,
                                        CreditsBalanceResponse,
                                        PaymentIntentResponse,
                                        SubscribeRequest, TransactionHistoryResponse,
                                        UsageStatsResponse, BuyCreditsPackageRequest)
from app.services.billing.credits_service import CreditsService
from app.services.billing.stripe_service import StripeService
from fastapi import APIRouter, Depends, Request, Query, status
from sqlalchemy import func, select
from shared.core.exceptions.domain_exceptions import StripeServiceException
from sqlalchemy.ext.asyncio import AsyncSession
from shared.models.database.usage_log import UsageLog
from shared.models.database.job import Job
from shared.models.database.stripe_price_config import StripePriceConfig
from shared.models.database.credits_transaction import CreditsTransaction
from shared.core.billing import MicroDollar

router = APIRouter(tags=["Billing"])

class ParseUsageResponse(BaseModel):
    """使用概览响应"""
    request_total: int
    mom_growth: float
    credits_used: int
    estimated_amount: Optional[float]
    success_rate: float
    avg_processing_time: float


@router.post("/subscribe", summary="订阅计划")
async def subscribe_plan(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """订阅计划"""
    stripe_service = StripeService()
    
    try:
        # 使用环境变量配置的前端URL
        frontend_url = settings.FRONTEND_URL
        success_url = f"{frontend_url}/billing?success=true&plan={request.plan_id}"
        cancel_url = f"{frontend_url}/billing?canceled=true"
        
        checkout_url = await stripe_service.create_checkout_session(
            db=db,
            user_id=str(current_user.id),
            plan_id=request.plan_id,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        return CheckoutSessionResponse(
            checkout_url=checkout_url,
            session_id=""
        )
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"创建订阅失败: {str(e)}"
        )


@router.post("/buy-credits", summary="购买Credits")
async def buy_credits(
    request: BuyCreditsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """购买Credits"""
    stripe_service = StripeService()
    
    try:
        # @TODO, whats going on here?
        # 计算金额（100 Credits = ¥2，即1 Credit = ¥0.02）
        amount_cny = request.credits_amount * 0.02  # 人民币金额
        amount_cents = int(amount_cny * 100)  # 转换为分
        
        payment_intent = await stripe_service.create_payment_intent(
            user_id=str(current_user.id),
            amount=amount_cents,
            credits_amount=request.credits_amount,
            currency='cny'
        )
        
        return PaymentIntentResponse(
            client_secret=payment_intent["client_secret"],
            payment_intent_id=payment_intent["payment_intent_id"]
        )
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"购买Credits失败: {str(e)}"
        )


@router.get("/subscription", summary="获取当前订阅信息")
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前订阅信息"""
    try:
        from app.repositories.subscription_repository import \
            SubscriptionRepository
        
        subscription_repo = SubscriptionRepository()
        subscription = await subscription_repo.get_active_by_user_id(db, str(current_user.id))
        
        if not subscription:
            # 返回默认的免费订阅
            return {
                "id": "free",
                "plan_type": "free",
                "status": "active",
                "start_date": current_user.create_time.isoformat(),
                "end_date": None,
                "credits_limit": 100,
                "stripe_subscription_id": None
            }
        
        return {
            "id": subscription.id,
            "plan_type": subscription.plan_type,
            "status": subscription.status,
            "start_date": subscription.start_date.isoformat(),
            "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
            "credits_limit": subscription.get_micro_dollar_limit().to_credit(),
            "stripe_subscription_id": subscription.stripe_subscription_id
        }
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"获取订阅信息失败: {str(e)}"
        )


@router.get("/credits", summary="获取Credits余额")
async def get_credits_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取Credits余额"""
    credits_service = CreditsService()
    
    try:
        balance_micro_dollar = await credits_service.check_balance(db, str(current_user.id))
        
        # 获取订阅信息计算限制
        from app.repositories.subscription_repository import \
            SubscriptionRepository
        subscription_repo = SubscriptionRepository()
        # TODO, need determine if a user can not have subscription?
        subscription = await subscription_repo.get_active_by_user_id(db, str(current_user.id))
        
        limit_micro_dollar = subscription.get_micro_dollar_limit() if subscription else MicroDollar.from_dollars(100).amount
        
        usage_percentage = (balance_micro_dollar / limit_micro_dollar * 100) if limit_micro_dollar > 0 else 0

        return CreditsBalanceResponse(
            credits_balance=MicroDollar(balance_micro_dollar).to_credit(),
            credits_limit=MicroDollar(limit_micro_dollar).to_credit(),
            usage_percentage=round(usage_percentage, 2)
        )
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"获取Credits余额失败: {str(e)}"
        )


@router.get("/usage", summary="获取使用统计")
async def get_usage_stats(
    period: str = "month",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取使用统计"""
    credits_service = CreditsService()
    
    try:
        stats = await credits_service.get_usage_stats(db, str(current_user.id), period)
        
        return UsageStatsResponse(
            period=stats["period"],
            total_credits_used=MicroDollar(stats["total_used"]).to_credit(),
            api_calls_count=stats["transaction_count"],
            success_rate=95.0,  # TODO: 从使用日志计算实际成功率
            average_response_time=stats.get("avg_response_time", 0),
            top_endpoints=[]  # TODO: 从使用日志获取热门端点
        )
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"获取使用统计失败: {str(e)}"
        )


@router.get("/parse-usage", summary="获取使用解析概览", response_model=ParseUsageResponse)
async def parse_usage_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    返回使用概览：
    - 请求总数
    - 同比上月增长（最近30天 vs 再前30天）
    - 已用积分（从credits_transactions表统计，包含usage和refund类型）
    - 预估金额（取第一个 credits_package 的单价：amount_cents/(100*credits_amount)）
    - 成功率（jobs: done 占所有状态总数）
    - 平均处理时间（jobs: updated_at - created_at，秒）
    """
    try:
        user_id = str(current_user.id)
        now = datetime.utcnow()
        current_start = now - timedelta(days=30)
        previous_start = now - timedelta(days=60)

        # 请求总数（从UsageLog表统计）
        request_row = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user_id)
        )
        total_requests = request_row.scalar_one() or 0

        # 已用积分：从credits_transactions表统计usage和refund类型
        # usage类型为负数（扣除），refund类型为正数（退还）
        # 净消耗 = abs(sum(usage + refund)), then convert to display credits
        credits_row = await db.execute(
            select(func.coalesce(func.sum(CreditsTransaction.credits_amount), 0))
            .where(CreditsTransaction.user_id == user_id)
            .where(CreditsTransaction.transaction_type.in_(["usage", "refund"]))
        )
        # Cast Decimal to int is safe here because:
        # 1. Source column is BigInteger (whole numbers only)
        # 2. Postgres returns Decimal to avoid overflow
        # 3. Sum of integers has no fractional part, so int() is lossless
        total_micro_credits_used = int(abs(credits_row.scalar_one() or 0)) 


        # 同比上月增长：最近30天 vs 前一个30天
        curr_row = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user_id)
            .where(UsageLog.created_at >= current_start)
        )
        prev_row = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user_id)
            .where(UsageLog.created_at >= previous_start)
            .where(UsageLog.created_at < current_start)
        )
        curr_count = curr_row.scalar_one() or 0
        prev_count = prev_row.scalar_one() or 0
        mom_growth = ((curr_count - prev_count) / prev_count * 100) if prev_count > 0 else 0.0

        # 成功率 & 平均处理时间
        job_row = await db.execute(
            select(
                func.count().filter(Job.status == "done").label("done_cnt"),
                func.count().label("total_cnt"),  # 所有状态的总数
                func.avg(func.extract("epoch", Job.updated_at - Job.created_at)).label("avg_secs"),
            ).where(Job.user_id == user_id)
        )
        job_stats = job_row.first() or (0, 0, 0.0)
        done_cnt = getattr(job_stats, "done_cnt", 0) or 0
        total_cnt = getattr(job_stats, "total_cnt", 0) or 0
        success_rate = (done_cnt / total_cnt * 100) if total_cnt > 0 else 0.0
        avg_processing_time = round(float(getattr(job_stats, "avg_secs", 0.0) or 0.0), 2)

        # 预估金额：credits_package的第一条配置
        price_row = await db.execute(
            select(StripePriceConfig)
            .where(StripePriceConfig.product_type == "credits_package")
            .where(StripePriceConfig.is_active.is_(True))
            .order_by(StripePriceConfig.created_at)
            .limit(1)
        )
        price_cfg = price_row.scalar_one_or_none()
        estimated_amount = None
        if price_cfg and price_cfg.credits_amount and price_cfg.credits_amount > 0:
            estimated_amount = round(price_cfg.amount_cents * total_micro_credits_used / (100 * price_cfg.credits_amount), 4)

        return ParseUsageResponse(
            request_total=total_requests or 0,
            mom_growth=round(mom_growth, 2),
            credits_used=MicroDollar(total_micro_credits_used).to_credit() or 0,
            estimated_amount=estimated_amount, # in dollar
            success_rate=round(success_rate, 2),
            avg_processing_time=avg_processing_time,
        )
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"获取使用解析概览失败: {str(e)}"
        )


@router.get("/history", summary="获取消费历史")
async def get_transaction_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取消费历史"""
    credits_service = CreditsService()
    
    try:
        transactions = await credits_service.get_transaction_history(db, str(current_user.id), limit)
        
        transaction_list = [
            TransactionHistoryResponse(
                id=tx.id,
                credits_amount=MicroDollar(tx.credits_amount).to_credit(),
                transaction_type=tx.transaction_type,
                description=tx.description,
                created_at=tx.created_at
            )
            for tx in transactions
        ]
        
        return transaction_list
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"获取消费历史失败: {str(e)}"
        )


@router.get("/price-configs", summary="获取价格配置列表")
async def get_price_configs(
    product_type: Optional[str] = Query(None, description="产品类型: subscription 或 credits_package"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取价格配置列表（订阅或Credits包）"""
    try:
        from app.services.billing.price_config_service import PriceConfigService
        
        price_config_service = PriceConfigService()
        
        if product_type == 'subscription':
            # 获取所有订阅类型配置
            configs = await price_config_service.repository.get_all_active(db)
            subscription_configs = [c for c in configs if c.product_type == 'subscription']
            return {
                "subscriptions": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": config.extra_metadata.get('display_name', config.plan_id.upper()) if config.extra_metadata else config.plan_id.upper(),
                        "description": config.extra_metadata.get('description', '') if config.extra_metadata else '',
                        "features": config.extra_metadata.get('features', []) if config.extra_metadata else [],
                        "popular": config.extra_metadata.get('frontend_config', {}).get('popular', False) if config.extra_metadata else False,
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {}
                    }
                    for config in subscription_configs
                ],
                "credits_packages": []
            }
        elif product_type == 'credits_package':
            # 获取所有Credits包配置
            credits_configs = await price_config_service.get_all_credits_packages(db)
            return {
                "subscriptions": [],
                "credits_packages": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": config.extra_metadata.get('display_name', f"{MicroDollar(config.credits_amount).to_credit()} Credits") if config.extra_metadata else f"{MicroDollar(config.credits_amount).to_credit()} Credits",
                        "description": config.extra_metadata.get('description', '') if config.extra_metadata else '',
                        "credits_amount": MicroDollar(config.credits_amount).to_credit(),
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {}
                    }
                    for config in credits_configs
                ]
            }
        else:
            # 获取所有配置
            configs = await price_config_service.repository.get_all_active(db)
            subscriptions = [c for c in configs if c.product_type == 'subscription']
            credits_packages = [c for c in configs if c.product_type == 'credits_package']
            
            return {
                "subscriptions": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": config.extra_metadata.get('display_name', config.plan_id.upper()) if config.extra_metadata else config.plan_id.upper(),
                        "description": config.extra_metadata.get('description', '') if config.extra_metadata else '',
                        "features": config.extra_metadata.get('features', []) if config.extra_metadata else [],
                        "popular": config.extra_metadata.get('frontend_config', {}).get('popular', False) if config.extra_metadata else False,
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {}
                    }
                    for config in subscriptions
                ],
                "credits_packages": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": config.extra_metadata.get('display_name', f"{MicroDollar(config.credits_amount).to_credit()} Credits") if config.extra_metadata else f"{MicroDollar(config.credits_amount).to_credit()} Credits",
                        "description": config.extra_metadata.get('description', '') if config.extra_metadata else '',
                        "credits_amount": MicroDollar(config.credits_amount).to_credit(),
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {}
                    }
                    for config in credits_packages
                ]
            }
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"获取价格配置失败: {str(e)}"
        )


@router.post("/buy-credits-package", summary="通过价格ID购买Credits包")
async def buy_credits_package(
    request: BuyCreditsPackageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """通过价格ID购买Credits包"""
    stripe_service = StripeService()
    
    try:
        # 使用环境变量配置的前端URL
        frontend_url = settings.FRONTEND_URL
        success_url = f"{frontend_url}/billing?success=true&type=credits_package"
        cancel_url = f"{frontend_url}/billing?canceled=true"
        
        checkout_url = await stripe_service.create_checkout_session_for_credits_package(
            db=db,
            user_id=str(current_user.id),
            price_id=request.price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            quantity=request.quantity
        )
        
        return CheckoutSessionResponse(
            checkout_url=checkout_url,
            session_id=""
        )
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"创建Credits包购买失败: {str(e)}"
        )


@router.post("/webhook", summary="Stripe Webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """处理Stripe Webhook"""
    stripe_service = StripeService()
    
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        result = await stripe_service.handle_webhook(db, payload, sig_header)
        
        # 如果是订阅完成事件，发送确认邮件
        if result.get('event_type') == 'checkout.session.completed' and result.get('payment_type') == 'subscription':
            await _send_purchase_confirmation_email(
                user_id=result.get('user_id'),
                plan_type=result.get('plan_id'),
                amount=result.get('amount', 0),
                db=db
            )
        
        return result
        
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Webhook处理失败: {str(e)}"
        )


async def _send_purchase_confirmation_email(user_id: str, plan_type: str, amount: float, db: AsyncSession):
    """发送购买确认邮件"""
    try:
        from shared.models.database.user import User
        from app.services.email import EmailService
        from sqlalchemy import select

        # 获取用户信息
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            email_service = EmailService()
            await email_service.send_purchase_confirmation_email(
                user_email=user.email,
                plan_type=plan_type,
                amount=amount,
                user_name=getattr(user, 'full_name', None) or user.email
            )
            
            from loguru import logger
            logger.info(f"购买确认邮件已发送给用户 {user.email}")
            
    except Exception as e:
        from loguru import logger
        logger.error(f"发送购买确认邮件失败: {e}")
        # 不抛出异常，避免影响Webhook处理
