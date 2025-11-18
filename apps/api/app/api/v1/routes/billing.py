"""
计费相关 API
"""

from shared.core.database import get_db
from app.core.dependencies import get_current_user
from shared.models.database.user import User
from shared.models.schemas.billing import (BuyCreditsRequest,
                                        CheckoutSessionResponse,
                                        CreditsBalanceResponse,
                                        PaymentIntentResponse,
                                        SubscribeRequest, TransactionHistoryResponse,
                                        UsageStatsResponse)
from app.services.billing.credits_service import CreditsService
from app.services.billing.stripe_service import StripeService
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Billing"])


@router.post("/subscribe", summary="订阅计划")
async def subscribe_plan(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """订阅计划"""
    stripe_service = StripeService()
    
    try:
        # 构建正确的成功和取消URL
        base_url = "http://localhost:3000"  # 开发环境，生产环境需要配置
        success_url = f"{base_url}/billing?success=true&plan={request.plan_id}"
        cancel_url = f"{base_url}/billing?canceled=true"
        
        checkout_url = await stripe_service.create_checkout_session(
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"创建订阅失败: {str(e)}"
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
        # 计算金额（100 Credits = ¥2，即1 Credit = ¥0.02）
        amount_cny = request.credits_amount * 0.02  # 人民币金额
        amount_cents = int(amount_cny * 100)  # 转换为分
        
        payment_intent = await stripe_service.create_payment_intent(
            user_id=str(current_user.id),
            amount=amount_cents,
            currency='cny'
        )
        
        return PaymentIntentResponse(
            client_secret=payment_intent["client_secret"],
            payment_intent_id=payment_intent["payment_intent_id"]
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"购买Credits失败: {str(e)}"
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
            "credits_limit": subscription.get_credits_limit(),
            "stripe_subscription_id": subscription.stripe_subscription_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取订阅信息失败: {str(e)}"
        )


@router.get("/credits", summary="获取Credits余额")
async def get_credits_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取Credits余额"""
    credits_service = CreditsService()
    
    try:
        balance = await credits_service.check_balance(db, str(current_user.id))
        
        # 获取订阅信息计算限制
        from app.repositories.subscription_repository import \
            SubscriptionRepository
        subscription_repo = SubscriptionRepository()
        subscription = await subscription_repo.get_active_by_user_id(db, str(current_user.id))
        
        credits_limit = subscription.get_credits_limit() if subscription else 100
        
        usage_percentage = (balance / credits_limit * 100) if credits_limit > 0 else 0
        
        return CreditsBalanceResponse(
            credits_balance=balance,
            credits_limit=credits_limit,
            usage_percentage=round(usage_percentage, 2)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Credits余额失败: {str(e)}"
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
            total_credits_used=stats["total_used"],
            api_calls_count=stats["transaction_count"],
            success_rate=95.0,  # TODO: 从使用日志计算实际成功率
            average_response_time=stats.get("avg_response_time", 0),
            top_endpoints=[]  # TODO: 从使用日志获取热门端点
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取使用统计失败: {str(e)}"
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
                credits_amount=tx.credits_amount,
                transaction_type=tx.transaction_type,
                description=tx.description,
                created_at=tx.created_at
            )
            for tx in transactions
        ]
        
        return transaction_list
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取消费历史失败: {str(e)}"
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
        
        result = await stripe_service.handle_webhook(payload, sig_header)
        
        # 如果是订阅完成事件，发送确认邮件
        if result.get('event_type') == 'checkout.session.completed':
            await _send_purchase_confirmation_email(
                user_id=result.get('user_id'),
                plan_type=result.get('plan_type'),
                amount=result.get('amount', 0),
                db=db
            )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook处理失败: {str(e)}"
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
