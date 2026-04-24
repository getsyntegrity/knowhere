"""
Billing API Routes
"""

from typing import Optional

from app.services.billing.stripe_service import StripeService
from app.services.rate_limit.dependencies import CurrentUser, with_current_user
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.billing import MicroDollar
from shared.core.config import settings
from shared.core.database import get_db
from shared.core.exceptions.domain_exceptions import StripeServiceException
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.job import Job
from shared.models.database.stripe_price_config import StripePriceConfig
from shared.models.schemas.billing import (
    BuyCreditsPackageRequest,
    BuyCreditsRequest,
    CheckoutSessionResponse,
    CreditsBalanceResponse,
    PaymentIntentResponse,
    TransactionHistoryResponse,
    UsageStatsResponse,
)
from shared.services.billing import CreditsService

router = APIRouter(tags=["Billing"])


class ParseUsageResponse(BaseModel):
    """Parse usage overview response"""

    request_total: int
    mom_growth: float
    credits_used: float
    estimated_amount: Optional[float]
    success_rate: float
    avg_processing_time: float


@router.post("/buy-credits", summary="Buy Credits")
async def buy_credits(
    request: BuyCreditsRequest,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buy credits via Stripe payment intent"""
    stripe_service = StripeService()

    try:
        # Calculate amount (100 Credits = ¥2, i.e. 1 Credit = ¥0.02)
        amount_cny = request.credits_amount * 0.02  # CNY amount
        amount_cents = int(amount_cny * 100)  # Convert to cents

        payment_intent = await stripe_service.create_payment_intent(
            user_id=current_user.user_id,
            amount=amount_cents,
            credits_amount=MicroDollar.from_dollars(request.credits_amount).amount,
            currency="cny",
        )

        return PaymentIntentResponse(
            client_secret=payment_intent["client_secret"],
            payment_intent_id=payment_intent["payment_intent_id"],
        )

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to buy credits: {str(e)}"
        )


@router.get(
    "/credits", summary="Get Credits Balance", response_model=CreditsBalanceResponse
)
async def get_credits_balance(
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current credits balance for the authenticated user"""
    credits_service = CreditsService()

    try:
        # Ensure user is initialized
        await credits_service.ensure_user_initialized(db, current_user.user_id)
        await db.commit()

        balance_micro_dollar = await credits_service.get_balance(
            db, current_user.user_id
        )

        return CreditsBalanceResponse(
            credits_balance=MicroDollar(balance_micro_dollar).to_credit()
        )

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to get credits balance: {str(e)}"
        )


@router.get("/usage", summary="Get Usage Statistics")
async def get_usage_stats(
    period: str = "month",
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage statistics for the authenticated user"""
    credits_service = CreditsService()

    try:
        stats = await credits_service.get_usage_stats(db, current_user.user_id, period)

        return UsageStatsResponse(
            period=stats["period"],
            total_credits_used=MicroDollar(stats["total_used"]).to_credit(),
            api_calls_count=stats["transaction_count"],
            success_rate=95.0,  # TODO: Calculate actual success rate from usage logs
            average_response_time=stats.get("avg_response_time", 0),
            top_endpoints=[],  # TODO: Get top endpoints from usage logs
        )

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to get usage statistics: {str(e)}"
        )


@router.get(
    "/parse-usage",
    summary="Get Parse Usage Overview",
    response_model=ParseUsageResponse,
)
async def parse_usage_overview(
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a usage overview:
    - Total request count (deprecated, always 0)
    - Month-over-month growth (deprecated, always 0)
    - Credits used (from credits_transactions table, including usage and refund types)
    - Estimated amount (using the first credits_package unit price: amount_cents / (100 * credits_amount))
    - Success rate (jobs: done out of terminal-state jobs)
    - Average processing time (jobs: updated_at - created_at, in seconds)
    """
    try:
        # request_total and mom_growth: UsageLog is deprecated, hardcoded to 0
        total_requests = 0
        mom_growth = 0.0

        # Credits used: sum usage and refund types from credits_transactions
        # Usage type is negative (deduction), refund type is positive (return)
        # Net consumption = abs(sum(usage + refund)), then convert to display credits
        credits_row = await db.execute(
            select(func.coalesce(func.sum(CreditsTransaction.credits_amount), 0))
            .where(CreditsTransaction.user_id == current_user.user_id)
            .where(CreditsTransaction.transaction_type.in_(["usage", "refund"]))
        )
        # Cast Decimal to int is safe here because:
        # 1. Source column is BigInteger (whole numbers only)
        # 2. Postgres returns Decimal to avoid overflow
        # 3. Sum of integers has no fractional part, so int() is lossless
        total_micro_credits_used = int(abs(credits_row.scalar_one() or 0))

        # Success rate & average processing time (terminal-state jobs only: done / failed)
        job_row = await db.execute(
            select(
                func.count().filter(Job.status == "done").label("done_cnt"),
                func.count()
                .filter(Job.status.in_(["done", "failed"]))
                .label("terminal_cnt"),
                func.avg(func.extract("epoch", Job.updated_at - Job.created_at)).label(
                    "avg_secs"
                ),
            ).where(Job.user_id == current_user.user_id)
        )
        job_stats = job_row.first() or (0, 0, 0.0)
        done_cnt = getattr(job_stats, "done_cnt", 0) or 0
        terminal_cnt = getattr(job_stats, "terminal_cnt", 0) or 0
        success_rate = (done_cnt / terminal_cnt * 100) if terminal_cnt > 0 else 0.0
        avg_processing_time = round(
            float(getattr(job_stats, "avg_secs", 0.0) or 0.0), 2
        )

        # Estimated amount: use the first credits_package price config
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
            estimated_amount = round(
                price_cfg.amount_cents
                * total_micro_credits_used
                / (100 * price_cfg.credits_amount),
                4,
            )

        return ParseUsageResponse(
            request_total=total_requests or 0,
            mom_growth=round(mom_growth, 2),
            credits_used=MicroDollar(total_micro_credits_used).to_credit() or 0,
            estimated_amount=estimated_amount,  # in dollar
            success_rate=round(success_rate, 2),
            avg_processing_time=avg_processing_time,
        )
    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to get parse usage overview: {str(e)}"
        )


@router.get("/history", summary="Get Transaction History")
async def get_transaction_history(
    limit: int = 50,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get credits transaction history for the authenticated user"""
    credits_service = CreditsService()

    try:
        transactions = await credits_service.get_transaction_history(
            db, current_user.user_id, limit
        )

        transaction_list = [
            TransactionHistoryResponse(
                id=tx.id,
                credits_amount=MicroDollar(tx.credits_amount).to_credit(),
                transaction_type=tx.transaction_type,
                description=tx.description,
                created_at=tx.created_at,
            )
            for tx in transactions
        ]

        return transaction_list

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to get transaction history: {str(e)}"
        )


@router.get("/price-configs", summary="Get Price Configurations")
async def get_price_configs(
    product_type: Optional[str] = Query(
        None, description="Product type: subscription or credits_package"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get price configuration list (subscriptions or credits packages)"""
    try:
        from app.services.billing.price_config_service import PriceConfigService

        price_config_service = PriceConfigService()

        if product_type == "subscription":
            # Get all subscription type configs
            configs = await price_config_service.repository.get_all_active(db)
            subscription_configs = [
                c for c in configs if c.product_type == "subscription"
            ]
            return {
                "subscriptions": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": (
                            config.extra_metadata.get(
                                "display_name", config.plan_id.upper()
                            )
                            if config.extra_metadata
                            else config.plan_id.upper()
                        ),
                        "description": (
                            config.extra_metadata.get("description", "")
                            if config.extra_metadata
                            else ""
                        ),
                        "features": (
                            config.extra_metadata.get("features", [])
                            if config.extra_metadata
                            else []
                        ),
                        "popular": (
                            config.extra_metadata.get("frontend_config", {}).get(
                                "popular", False
                            )
                            if config.extra_metadata
                            else False
                        ),
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {},
                    }
                    for config in subscription_configs
                ],
                "credits_packages": [],
            }
        elif product_type == "credits_package":
            # Get all credits package configs
            credits_configs = await price_config_service.get_all_credits_packages(db)
            return {
                "subscriptions": [],
                "credits_packages": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": (
                            config.extra_metadata.get(
                                "display_name",
                                f"{MicroDollar(config.credits_amount).to_credit()} Credits",
                            )
                            if config.extra_metadata
                            else f"{MicroDollar(config.credits_amount).to_credit()} Credits"
                        ),
                        "description": (
                            config.extra_metadata.get("description", "")
                            if config.extra_metadata
                            else ""
                        ),
                        "credits_amount": MicroDollar(
                            config.credits_amount
                        ).to_credit(),
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {},
                    }
                    for config in credits_configs
                ],
            }
        else:
            # Get all configs
            configs = await price_config_service.repository.get_all_active(db)
            subscriptions = [c for c in configs if c.product_type == "subscription"]
            credits_packages = [
                c for c in configs if c.product_type == "credits_package"
            ]

            return {
                "subscriptions": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": (
                            config.extra_metadata.get(
                                "display_name", config.plan_id.upper()
                            )
                            if config.extra_metadata
                            else config.plan_id.upper()
                        ),
                        "description": (
                            config.extra_metadata.get("description", "")
                            if config.extra_metadata
                            else ""
                        ),
                        "features": (
                            config.extra_metadata.get("features", [])
                            if config.extra_metadata
                            else []
                        ),
                        "popular": (
                            config.extra_metadata.get("frontend_config", {}).get(
                                "popular", False
                            )
                            if config.extra_metadata
                            else False
                        ),
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {},
                    }
                    for config in subscriptions
                ],
                "credits_packages": [
                    {
                        "id": config.plan_id,
                        "plan_id": config.plan_id,
                        "price_id": config.price_id,
                        "name": (
                            config.extra_metadata.get(
                                "display_name",
                                f"{MicroDollar(config.credits_amount).to_credit()} Credits",
                            )
                            if config.extra_metadata
                            else f"{MicroDollar(config.credits_amount).to_credit()} Credits"
                        ),
                        "description": (
                            config.extra_metadata.get("description", "")
                            if config.extra_metadata
                            else ""
                        ),
                        "credits_amount": MicroDollar(
                            config.credits_amount
                        ).to_credit(),
                        "amount_cents": config.amount_cents,
                        "currency": config.currency,
                        "metadata": config.extra_metadata or {},
                    }
                    for config in credits_packages
                ],
            }

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to get price configurations: {str(e)}"
        )


@router.post("/buy-credits-package", summary="Buy Credits Package by Price ID")
async def buy_credits_package(
    request: BuyCreditsPackageRequest,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buy a credits package by its Stripe price ID"""
    from sqlalchemy import select

    from shared.models.database.user import User

    stripe_service = StripeService()

    try:
        # Query user email from database
        result = await db.execute(
            select(User.email).where(User.id == current_user.user_id)
        )
        user_email = result.scalar_one_or_none()

        frontend_url = settings.FRONTEND_URL
        success_url = f"{frontend_url}/billing?success=true&type=credits_package"
        cancel_url = f"{frontend_url}/billing?canceled=true"

        checkout_url = await stripe_service.create_checkout_session_for_credits_package(
            db=db,
            user_id=current_user.user_id,
            price_id=request.price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            quantity=request.quantity,
            email=user_email,
        )

        return CheckoutSessionResponse(checkout_url=checkout_url, session_id="")

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to create credits package purchase: {str(e)}"
        )


@router.post("/webhook", summary="Stripe Webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhook events"""
    stripe_service = StripeService()

    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        if not sig_header:
            raise StripeServiceException(
                internal_message="Missing stripe-signature header"
            )

        result = await stripe_service.handle_webhook(db, payload, sig_header)

        return result

    except Exception as e:
        raise StripeServiceException(
            internal_message=f"Failed to handle webhook: {str(e)}"
        )
