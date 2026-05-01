from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.billing import MicroDollar
from shared.core.database import engine
from shared.models.database.api_key import APIKey
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user import User
from shared.models.database.user_balance import UserBalance
from shared.services.auth.user_table_bootstrap import ensure_better_auth_user_table
from shared.utils.api_key_hashing import hash_api_key


class LocalDevelopmentBootstrapService:
    """Bootstrap local-only user and billing state for development."""

    LOCAL_DEV_USER_ID: str = "local-dev-user"
    LOCAL_DEV_USER_NAME: str = "Local Development User"
    LOCAL_DEV_USER_EMAIL: str = "local-dev-user@knowhere.local"
    LOCAL_DEV_TIER: str = "tier_5"
    LOCAL_DEV_API_KEY_ID: str = "local-dev-default-api-key"
    LOCAL_DEV_API_KEY: str = "sk_local_dev_demo_key_tier5_full_access"
    LOCAL_DEV_API_KEY_NAME: str = "local-dev-full-access"
    LOCAL_DEV_PAYMENT_RECORD_ID: str = "local-dev-seed-payment-record"
    LOCAL_DEV_PAYMENT_INTENT_ID: str = "local-dev-seed-highest-tier"
    LOCAL_DEV_CREDITS_TRANSACTION_ID: str = "local-dev-seed-credit-entry"
    LOCAL_DEV_CREDITS_BALANCE: int = MicroDollar.from_dollars(2_000).amount
    LOCAL_DEV_LIFETIME_BILLING_MICRO: int = MicroDollar.from_dollars(2_000).amount
    LOCAL_DEV_PAYMENT_AMOUNT_CENTS: int = 200_000
    LOCAL_DEV_FALLBACK_EMAIL_DOMAIN: str = "knowhere.local"

    async def ensure_user_table_exists(self) -> None:
        """Create a dashboard-compatible local `user` table needed by API foreign keys."""
        async with engine.begin() as connection:
            await connection.run_sync(
                ensure_better_auth_user_table,
                fallback_email_domain=self.LOCAL_DEV_FALLBACK_EMAIL_DOMAIN,
            )

    async def seed_local_developer(self, session: AsyncSession) -> None:
        """Create or refresh the deterministic local top-tier developer account."""
        await self._upsert_user(session)
        await self._upsert_user_balance(session)
        await self._upsert_payment_record(session)
        await self._upsert_credits_transaction(session)
        await self._upsert_api_key(session)
        await session.flush()

    @classmethod
    def get_local_developer_profile(cls) -> dict[str, str | int]:
        """Expose deterministic local developer profile details for local tooling."""
        profile: dict[str, str | int] = {
            "user_id": cls.LOCAL_DEV_USER_ID,
            "name": cls.LOCAL_DEV_USER_NAME,
            "email": cls.LOCAL_DEV_USER_EMAIL,
            "tier": cls.LOCAL_DEV_TIER,
            "credits_balance": cls.LOCAL_DEV_CREDITS_BALANCE,
            "lifetime_billing_micro": cls.LOCAL_DEV_LIFETIME_BILLING_MICRO,
        }
        return profile

    @classmethod
    def get_local_developer_auth_profile(cls) -> dict[str, str | int]:
        """Expose deterministic local developer auth details for contract tests."""
        auth_profile = cls.get_local_developer_profile()
        auth_profile["api_key"] = cls.LOCAL_DEV_API_KEY
        return auth_profile

    async def _upsert_user(self, session: AsyncSession) -> None:
        user = await session.get(User, self.LOCAL_DEV_USER_ID)
        if user is None:
            session.add(
                User(
                    id=self.LOCAL_DEV_USER_ID,
                    name=self.LOCAL_DEV_USER_NAME,
                    email=self.LOCAL_DEV_USER_EMAIL,
                )
            )
            return

        user.name = self.LOCAL_DEV_USER_NAME
        user.email = self.LOCAL_DEV_USER_EMAIL

    async def _upsert_user_balance(self, session: AsyncSession) -> None:
        balance = await session.get(UserBalance, self.LOCAL_DEV_USER_ID)
        if balance is None:
            session.add(
                UserBalance(
                    user_id=self.LOCAL_DEV_USER_ID,
                    user_tier=self.LOCAL_DEV_TIER,
                    credits_balance=self.LOCAL_DEV_CREDITS_BALANCE,
                )
            )
            return

        balance.user_tier = self.LOCAL_DEV_TIER
        balance.credits_balance = self.LOCAL_DEV_CREDITS_BALANCE

    async def _upsert_payment_record(self, session: AsyncSession) -> None:
        payment = await session.get(PaymentRecord, self.LOCAL_DEV_PAYMENT_RECORD_ID)
        if payment is None:
            session.add(
                PaymentRecord(
                    id=self.LOCAL_DEV_PAYMENT_RECORD_ID,
                    payment_intent_id=self.LOCAL_DEV_PAYMENT_INTENT_ID,
                    user_id=self.LOCAL_DEV_USER_ID,
                    payment_type="local_dev_seed",
                    amount_cents=self.LOCAL_DEV_PAYMENT_AMOUNT_CENTS,
                    currency="USD",
                    status="succeeded",
                    credits_amount=self.LOCAL_DEV_LIFETIME_BILLING_MICRO,
                    processed_at=self._utc_now(),
                    extra_metadata={"reason": "local_dev_seed"},
                )
            )
            return

        payment.payment_intent_id = self.LOCAL_DEV_PAYMENT_INTENT_ID
        payment.user_id = self.LOCAL_DEV_USER_ID
        payment.payment_type = "local_dev_seed"
        payment.amount_cents = self.LOCAL_DEV_PAYMENT_AMOUNT_CENTS
        payment.currency = "USD"
        payment.status = "succeeded"
        payment.credits_amount = self.LOCAL_DEV_LIFETIME_BILLING_MICRO
        payment.processed_at = self._utc_now()
        payment.extra_metadata = {"reason": "local_dev_seed"}

    async def _upsert_credits_transaction(self, session: AsyncSession) -> None:
        transaction = await session.get(
            CreditsTransaction,
            self.LOCAL_DEV_CREDITS_TRANSACTION_ID,
        )
        if transaction is None:
            session.add(
                CreditsTransaction(
                    id=self.LOCAL_DEV_CREDITS_TRANSACTION_ID,
                    user_id=self.LOCAL_DEV_USER_ID,
                    credits_amount=self.LOCAL_DEV_CREDITS_BALANCE,
                    transaction_type="local_dev_seed",
                    description="Local development seed credits",
                    transaction_metadata={"reason": "local_dev_seed"},
                )
            )
            return

        transaction.user_id = self.LOCAL_DEV_USER_ID
        transaction.credits_amount = self.LOCAL_DEV_CREDITS_BALANCE
        transaction.transaction_type = "local_dev_seed"
        transaction.description = "Local development seed credits"
        transaction.transaction_metadata = {"reason": "local_dev_seed"}

    async def _upsert_api_key(self, session: AsyncSession) -> None:
        api_key = await session.get(APIKey, self.LOCAL_DEV_API_KEY_ID)
        key_hash = hash_api_key(self.LOCAL_DEV_API_KEY)
        key_mask = self._mask_api_key(self.LOCAL_DEV_API_KEY)

        if api_key is None:
            session.add(
                APIKey(
                    id=self.LOCAL_DEV_API_KEY_ID,
                    user_id=self.LOCAL_DEV_USER_ID,
                    key_hash=key_hash,
                    key_mask=key_mask,
                    name=self.LOCAL_DEV_API_KEY_NAME,
                    enabled_modules=["all"],
                )
            )
            return

        api_key.user_id = self.LOCAL_DEV_USER_ID
        api_key.key_hash = key_hash
        api_key.key_mask = key_mask
        api_key.name = self.LOCAL_DEV_API_KEY_NAME
        api_key.enabled_modules = ["all"]
        api_key.is_active = True

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        if len(api_key) < 12:
            return api_key
        return api_key[:8] + "•" * (len(api_key) - 12) + api_key[-4:]

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)
