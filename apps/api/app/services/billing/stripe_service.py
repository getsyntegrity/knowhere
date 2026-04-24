"""Stripe payment service."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

import stripe
from app.repositories.payment_record_repository import PaymentRecordRepository
from app.services.billing.price_config_service import PriceConfigService
from app.services.rate_limit.identity_cache import identity_cache
from app.services.rate_limit.tier_service import TierService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.config import redis_pool_manager, settings
from shared.core.exceptions.domain_exceptions import (
    AuthException,
    KnowhereException,
    StripeServiceException,
    SystemSettingMissingException,
    ValidationException,
)
from shared.core.logging import logger
from shared.models.database.payment_record import PaymentRecord
from shared.repositories.credits_repository import CreditsRepository
from shared.services.billing import CreditsService


class StripeService:
    """Stripe payment service."""

    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            raise SystemSettingMissingException(
                internal_message="Stripe API key not configured (STRIPE_SECRET_KEY)"
            )
        stripe.api_key = settings.STRIPE_SECRET_KEY
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
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout session for a subscription."""
        try:
            # Load the Stripe price ID for the requested plan from the database.
            price_id = await self.price_config_service.get_plan_price_id(db, plan_id)

            session = stripe.checkout.Session.create(
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "type": "subscription",
                },
                allow_promotion_codes=True,
                # Disable Adaptive Pricing to prevent currency switcher from hiding Alipay.
                # Alipay handles USD→CNY conversion internally for customers.
                adaptive_pricing={"enabled": False},
            )
            return str(session.url or "")
        except stripe.StripeError as e:
            logger.error(f"Failed to create subscription checkout session: {e}")
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
        email: Optional[str] = None,
    ) -> str:
        """Create a Stripe Checkout session for a credits package."""
        try:
            # Validate that the selected price configuration exists.
            config = await self.price_config_service.get_price_config(db, price_id)
            if not config.is_credits_package():
                raise ValidationException(
                    user_message="Invalid price configuration",
                    violations=[
                        {
                            "field": "price_id",
                            "description": f"Price ID {price_id} is not a credits package",
                        }
                    ],
                )

            # Ensure user is initialized (UserBalance exists)
            await self.credits_service.ensure_user_initialized(db, user_id)

            user_balance = await self.credits_repo.get_user_balance(db, user_id)
            if not user_balance:
                # Should not happen after ensure_user_initialized
                raise ValidationException(
                    user_message="Failed to initialize user balance",
                    violations=[
                        {
                            "field": "user_id",
                            "description": f"Failed to initialize user balance for {user_id}",
                        }
                    ],
                )

            customer_id = user_balance.stripe_customer_id

            if not customer_id:
                # Reuse an existing Stripe customer when the email already exists.
                if email:
                    existing_customers = stripe.Customer.list(email=email, limit=1)
                    if existing_customers.data:
                        customer_id = existing_customers.data[0].id

                if not customer_id:
                    # Create a new Stripe customer when no existing record matches.
                    if not email:
                        # For new customers, we prefer having an email.
                        # If no email provided, we can't create a good customer record.
                        # But technically Stripe allows it.
                        # Better: Require email for new billing profiles.
                        raise ValidationException(
                            user_message="Email required for first-time payment",
                            violations=[
                                {
                                    "field": "email",
                                    "description": "Email is required to create a billing profile",
                                }
                            ],
                        )

                    customer_params = {
                        "email": email,
                        "metadata": {"user_id": str(user_id)},
                    }
                    # Username is not available without User model, omit it.

                    customer = stripe.Customer.create(**customer_params)
                    customer_id = customer.id

                user_balance.stripe_customer_id = customer_id

            # Keep metadata values as strings so refunds can recover the user ID later.
            metadata = {
                "user_id": str(user_id),
                "price_id": str(price_id),
                "type": "credits_package",
                "credits_amount": (
                    str(config.credits_amount) if config.credits_amount else None
                ),
                "quantity": str(quantity),
            }

            session_params: Dict[str, Any] = {
                "customer": customer_id,
                "customer_update": {"address": "auto"},
                "client_reference_id": str(user_id),
                "line_items": [
                    {
                        "price": price_id,
                        "quantity": quantity,
                    }
                ],
                "mode": "payment",  # One-time payment.
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata,
                # Copy metadata onto the PaymentIntent and Charge for refund handling.
                "payment_intent_data": {
                    "metadata": metadata,
                },
                # Collect more customer information for later reconciliation.
                "allow_promotion_codes": True,
                # Disable Adaptive Pricing to prevent currency switcher from hiding Alipay.
                # Alipay handles USD→CNY conversion internally for customers.
                "adaptive_pricing": {"enabled": False},
                # Require a billing address so Checkout syncs it to the customer record.
                "billing_address_collection": "required",
            }

            session = stripe.checkout.Session.create(**session_params)

            await db.commit()

            return str(session.url or "")
        except stripe.StripeError as e:
            logger.error(f"Stripe credits checkout session failed: {e}")
            raise StripeServiceException(
                internal_message=f"Stripe credits checkout session failed: {e}"
            )

    async def create_payment_intent(
        self, user_id: str, amount: int, credits_amount: int, currency: str = "usd"
    ) -> Dict[str, Any]:
        """Create a PaymentIntent for a credits purchase."""
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,  # amount in cents
                currency=currency,
                automatic_payment_methods={"enabled": True},
                metadata={
                    "user_id": user_id,
                    "type": "credits",
                    "credits_amount": str(credits_amount),
                },
            )
            return {
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
            }
        except stripe.StripeError as e:
            logger.error(f"Failed to create payment intent: {e}")
            raise StripeServiceException(
                internal_message=f"Stripe payment intent creation failed: {e}"
            )

    async def handle_webhook(
        self, db: AsyncSession, payload: bytes, sig_header: str
    ) -> Dict[str, Any]:
        """Handle a Stripe webhook payload."""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return await self._process_webhook_event(db, event)
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            raise ValidationException(
                user_message="Invalid webhook payload",
                violations=[
                    {"field": "payload", "description": "Webhook payload is malformed"}
                ],
            )
        except stripe.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {e}")
            raise AuthException(
                user_message="Invalid webhook signature",
                internal_message=f"Webhook signature verification failed: {e}",
            )

    async def _process_webhook_event(
        self, db: AsyncSession, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch an incoming Stripe webhook event."""
        event_type = event["type"]

        if event_type == "checkout.session.completed":
            return await self._handle_checkout_completed(db, event)
        elif event_type == "payment_intent.succeeded":
            return await self._handle_payment_intent_succeeded(db, event)
        elif event_type == "invoice.payment_succeeded":
            return await self._handle_payment_succeeded(db, event)
        elif event_type == "customer.subscription.deleted":
            return await self._handle_subscription_deleted(db, event)
        elif event_type == "charge.refunded":
            return await self._handle_charge_refunded(db, event)
        else:
            return {"status": "ignored", "event_type": event_type}

    async def _handle_checkout_completed(
        self, db: AsyncSession, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle a completed Checkout session."""
        session = event["data"]["object"]
        session_id = session["id"]
        mode = session.get("mode")
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        payment_type = metadata.get("type")
        quantity = int(metadata.get("quantity", 1))

        if not user_id:
            logger.warning(
                f"Checkout session {session_id} is missing user_id metadata; likely a test event, skipping"
            )
            return {
                "status": "ignored",
                "message": "Missing user_id metadata (likely test event)",
                "checkout_session_id": session_id,
                "event_type": "checkout.session.completed",
            }

        # Skip work that was already processed for this Checkout session.
        if await self.payment_record_repo.is_processed(
            db, checkout_session_id=session_id
        ):
            logger.info(f"Checkout session {session_id} already processed, skipping")
            return {
                "status": "ignored",
                "message": "Already processed",
                "checkout_session_id": session_id,
            }

        # Seed audit metadata for the payment record.
        payment_metadata = {
            "session_id": session_id,
            "stripe_session": session,  # Full session payload for debugging and audits.
        }

        # Create the pending payment record before side effects run.
        payment_record = PaymentRecord(
            checkout_session_id=session_id,
            user_id=user_id,
            payment_type=payment_type or "unknown",
            amount_cents=session.get("amount_total", 0),
            currency=session.get("currency", "cny").upper(),
            status="pending",
            extra_metadata=payment_metadata,
        )
        db.add(payment_record)
        await db.flush()  # Get the database ID without committing yet.

        try:
            if mode == "payment" and payment_type == "credits_package":
                # Credits package purchase flow.
                price_id = metadata.get("price_id")

                if not price_id:
                    logger.error(f"Incomplete Credits pack info: price_id={price_id}")
                    return {"status": "error", "message": "Missing price_id"}

                # Load the credits amount and product metadata from the price config.
                price_config = await self.price_config_service.get_price_config(
                    db, price_id
                )
                credits_amount = price_config.credits_amount * quantity
                if credits_amount is None:
                    logger.error(
                        f"Credits amount is not configured for price ID {price_id}"
                    )
                    return {
                        "status": "error",
                        "message": "Credits amount not configured",
                    }

                # Attach purchased product details to the payment record.
                product_description = f"Credits pack - {credits_amount} Credits"
                if price_config.extra_metadata and price_config.extra_metadata.get(
                    "description"
                ):
                    product_description = price_config.extra_metadata.get("description")

                payment_record.extra_metadata = {
                    **payment_metadata,
                    "product_description": product_description,
                    "price_id": price_id,
                    "credits_amount": credits_amount,
                    "product_metadata": price_config.extra_metadata
                    or {},  # Product metadata from the price config.
                }

                # Grant the purchased credits to the user balance.
                await self.credits_service.add_credits(
                    session=db,
                    user_id=user_id,
                    amount=credits_amount,
                    reason=f"Purchase credits pack: {product_description}",
                    stripe_payment_id=session.get("payment_intent"),
                )

                # Mark the payment record as completed.
                payment_record.status = "succeeded"
                payment_record.credits_amount = credits_amount
                payment_record.processed_at = datetime.utcnow()

                await TierService.refresh_tier(user_id, db)
                await db.commit()
                await db.refresh(payment_record)

                await identity_cache.invalidate_user(
                    redis_pool_manager.get_redis_service(),
                    user_id,
                )

                logger.info(
                    f"Credits pack purchase succeeded: user_id={user_id}, credits={credits_amount}, price_id={price_id}"
                )
                return {
                    "status": "success",
                    "event_type": "checkout.session.completed",
                    "user_id": user_id,
                    "credits_amount": credits_amount,
                    "payment_type": "credits_package",
                }
            else:
                logger.warning(
                    f"Unknown payment type: mode={mode}, type={payment_type}"
                )
                return {"status": "ignored", "message": "Unknown payment type"}

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to process checkout.session.completed: {e}", exc_info=True
            )
            payment_record.status = "failed"
            payment_record.extra_metadata = {
                **(payment_record.extra_metadata or {}),
                "error": str(e),
            }
            await db.commit()
            raise StripeServiceException(
                internal_message=f"Failed to process checkout.session.completed: {str(e)}",
                original_exception=e,
            )

    async def _handle_payment_intent_succeeded(
        self, db: AsyncSession, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle a successful PaymentIntent for a credits purchase."""
        payment_intent = event["data"]["object"]
        payment_intent_id = payment_intent["id"]
        metadata = payment_intent.get("metadata", {})
        user_id = metadata.get("user_id")
        payment_type = metadata.get("type")

        if payment_type != "credits":
            logger.info(
                f"PaymentIntent {payment_intent_id} is not a Credits payment, skipping"
            )
            return {"status": "ignored", "payment_intent_id": payment_intent_id}

        if not user_id:
            logger.warning(
                f"PaymentIntent {payment_intent_id} is missing user_id metadata; likely a test event, skipping"
            )
            return {
                "status": "ignored",
                "message": "Missing user_id metadata (likely test event)",
                "payment_intent_id": payment_intent_id,
            }

        # Skip work that was already processed for this PaymentIntent.
        if await self.payment_record_repo.is_processed(
            db, payment_intent_id=payment_intent_id
        ):
            logger.info(
                f"PaymentIntent {payment_intent_id} already processed, skipping"
            )
            return {
                "status": "ignored",
                "message": "Already processed",
                "payment_intent_id": payment_intent_id,
            }

        # Seed audit metadata for the payment record.
        payment_metadata = {
            "payment_intent_id": payment_intent_id,
            "stripe_payment_intent": payment_intent,  # Full PaymentIntent payload for debugging and audits.
        }

        # Create the pending payment record before side effects run.
        payment_record = PaymentRecord(
            payment_intent_id=payment_intent_id,
            user_id=user_id,
            payment_type="credits_package",
            amount_cents=payment_intent.get("amount", 0),
            currency=payment_intent.get("currency", "cny").upper(),
            status="pending",
            extra_metadata=payment_metadata,
        )
        db.add(payment_record)
        await db.flush()  # Get the database ID without committing yet.

        try:
            # Read the purchased credits amount from metadata.
            credits_amount_str = metadata.get("credits_amount")
            if not credits_amount_str:
                logger.error(
                    f"PaymentIntent {payment_intent_id} is missing credits_amount"
                )
                payment_record.status = "failed"
                payment_record.extra_metadata = {
                    **(payment_record.extra_metadata or {}),
                    "error": "Missing credits_amount",
                }
                await db.commit()
                return {"status": "error", "message": "Missing credits_amount"}

            credits_amount = int(credits_amount_str)

            # Attach purchased product details to the payment record.
            payment_record.extra_metadata = {
                **payment_metadata,
                "product_description": f"Credits package - {credits_amount} Credits",
                "credits_amount": credits_amount,
                "payment_method": "payment_intent",  # Marks this purchase as PaymentIntent-based.
            }

            # Amount validation can be layered in here if needed later.
            payment_intent.get("amount", 0)

            # Grant the purchased credits to the user balance.
            await self.credits_service.add_credits(
                session=db,
                user_id=user_id,
                amount=credits_amount,
                reason=f"buy credits - {credits_amount} Credits",
                stripe_payment_id=payment_intent_id,
            )

            # Mark the payment record as completed.
            payment_record.status = "succeeded"
            payment_record.credits_amount = credits_amount
            payment_record.processed_at = datetime.utcnow()

            await TierService.refresh_tier(user_id, db)
            await db.commit()
            await db.refresh(payment_record)

            await identity_cache.invalidate_user(
                redis_pool_manager.get_redis_service(),
                user_id,
            )

            logger.info(
                f"buy credits success: user_id={user_id}, credits={credits_amount}, payment_intent_id={payment_intent_id}"
            )
            return {
                "status": "success",
                "event_type": "payment_intent.succeeded",
                "user_id": user_id,
                "credits_amount": credits_amount,
                "payment_type": "credits_package",
            }

        except Exception as e:
            logger.error(f"Failed to process Credits purchase: {e}", exc_info=True)
            payment_record.status = "failed"
            payment_record.extra_metadata = {
                **(payment_record.extra_metadata or {}),
                "error": str(e),
            }
            await db.commit()
            raise StripeServiceException(
                internal_message=f"Failed to process Credits purchase: {str(e)}",
                original_exception=e,
            )

    async def _handle_payment_succeeded(
        self, db: AsyncSession, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle a successful subscription renewal payment."""
        invoice = event["data"]["object"]
        subscription_id = invoice.get("subscription")

        if not subscription_id:
            logger.warning("Invoice is missing subscription ID")
            return {"status": "ignored", "message": "Missing subscription_id"}

        return {"status": "ignored", "message": "Subscription renewal not implemented"}

    async def _handle_subscription_deleted(
        self, db: AsyncSession, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle subscription deletion events."""
        subscription = event["data"]["object"]
        stripe_subscription_id = subscription["id"]

        try:
            # Subscription management not yet implemented
            logger.warning(
                f"Local subscription record not found: stripe_subscription_id={stripe_subscription_id}"
            )

            return {"status": "success", "subscription_id": stripe_subscription_id}
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to process customer.subscription.deleted: {e}", exc_info=True
            )
            raise StripeServiceException(
                internal_message=f"Failed to process customer.subscription.deleted: {str(e)}",
                original_exception=e,
            )

    async def _handle_charge_refunded(
        self, db: AsyncSession, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle refund events, including manual refunds from the Stripe dashboard."""
        charge = event["data"]["object"]
        charge_id = charge.get("id")
        refund_items = (charge.get("refunds", {}) or {}).get("data", []) or []
        latest_refund = refund_items[-1] if refund_items else None

        payment_intent_id = charge.get("payment_intent")
        refund_id = latest_refund.get("id") if latest_refund else None

        currency = (charge.get("currency") or "cny").upper()

        # Use a stable idempotency key derived from the refund or charge identifier.
        idempotency_key = refund_id or f"{charge_id}-refund"

        # Recover the original payment record to reuse billing context such as user_id.
        original_record = None
        if payment_intent_id:
            original_record = await self.payment_record_repo.get_by_payment_intent_id(
                db, payment_intent_id
            )

        metadata = charge.get("metadata") or {}
        user_id = metadata.get("user_id") or (getattr(original_record, "user_id", None))
        payment_type = (
            metadata.get("type")
            or (getattr(original_record, "payment_type", None))
            or "refund"
        )

        if not user_id:
            logger.error(
                f"Refund event is missing user_id; cannot record refund: charge_id={charge_id}"
            )
            return {
                "status": "error",
                "message": "Missing user_id for refund",
                "event_type": "charge.refunded",
            }

        # Normalize user_id to UUID before using it in SQL filters.
        if user_id and isinstance(user_id, str):
            try:
                user_id = UUID(user_id)
            except ValueError:
                logger.error(f"Invalid user_id format: {user_id}")
                return {
                    "status": "error",
                    "message": "Invalid user_id format",
                    "event_type": "charge.refunded",
                }

        user_id_str = str(user_id)

        # Compute the incremental refund amount from the cumulative Stripe total.
        # total_refund_amount_cents already includes the current refund event.
        total_refund_amount_cents = charge.get("amount_refunded") or 0

        # Load previously recorded refund totals for the same payment flow.
        origin_total_refund_amount_cents = 0

        # Sum historical refund records that use the same synthetic refund key.
        query = (
            select(func.sum(PaymentRecord.amount_cents))
            .where(PaymentRecord.payment_intent_id == idempotency_key)
            .where(PaymentRecord.user_id == user_id)
            .where(
                PaymentRecord.amount_cents
                < 0  # Refund rows are stored as negative amounts.
            )
        )
        result = await db.execute(query)
        # Sum negative refund amounts and convert back to a positive total.
        origin_total_refund_amount_cents = abs(result.scalar() or 0)

        refund_amount_cents = (
            total_refund_amount_cents - origin_total_refund_amount_cents
        )
        if refund_amount_cents <= 0:
            # The refund has already been processed; keep this path idempotent.
            logger.info(
                f"Refund already processed, skipping: charge_id={charge_id}, refund_id={refund_id}"
            )
            return {
                "status": "success",
                "event_type": "charge.refunded",
                "message": "Already processed",
                "user_id": user_id,
                "refund_id": refund_id,
            }

        # Translate the refunded cash amount back into credits using price metadata.
        credits_refunded = None
        price_id = metadata.get("price_id") or (
            getattr(original_record, "extra_metadata", {}) or {}
        ).get("price_id")
        if price_id:
            try:
                price_cfg = await self.price_config_service.get_price_config(
                    db, price_id
                )
                if price_cfg and price_cfg.amount_cents:
                    credits_refunded = -int(
                        price_cfg.credits_amount
                        * abs(refund_amount_cents)
                        / abs(price_cfg.amount_cents)  # credits_amount * quantity
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to calculate refunded Credits, price_id={price_id}: {e}"
                )
                credits_refunded = None

        # Fall back to the original payment record ratio when price metadata is unavailable.
        if (
            credits_refunded is None
            and original_record
            and original_record.credits_amount
            and original_record.amount_cents
        ):
            credits_refunded = -int(
                abs(original_record.credits_amount)
                * abs(refund_amount_cents)
                / abs(original_record.amount_cents)
            )

        # Apply the credit adjustment to the user balance when needed.
        if credits_refunded is not None and credits_refunded < 0:
            await self.credits_service.add_credits(
                session=db,
                user_id=user_id_str,
                amount=credits_refunded,
                reason="Refund adjustment",
                transaction_type="refund",
                transaction_metadata={"refund_id": refund_id, "charge_id": charge_id},
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
            stripe_subscription_id=getattr(
                original_record, "stripe_subscription_id", None
            ),
            processed_at=datetime.utcnow(),
            extra_metadata=refund_metadata,
        )

        db.add(refund_record)
        await db.commit()
        await db.refresh(refund_record)

        logger.info(
            f"Refund record created: user_id={user_id}, amount_cents={refund_record.amount_cents}, "
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
