from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.billing import MicroDollar
from shared.core.database import engine
from shared.models.database.api_key import APIKey
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user import User
from shared.models.database.user_balance import UserBalance


class LocalDevelopmentBootstrapService:
    """Bootstrap local-only user and billing state for development."""

    LOCAL_DEV_USER_ID: str = "local-dev-user"
    LOCAL_DEV_USER_NAME: str = "Local Development User"
    LOCAL_DEV_USER_EMAIL: str = "local-dev-user@knowhere.local"
    LOCAL_DEV_TIER: str = "tier_5"
    LOCAL_DEV_API_KEY_ID: str = "local-dev-default-api-key"
    LOCAL_DEV_API_KEY: str = "local_dev_demo_key_tier5_full_access"
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
            await connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS "user" (
                        id TEXT PRIMARY KEY NOT NULL,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        "emailVerified" BOOLEAN DEFAULT false NOT NULL,
                        image TEXT,
                        role TEXT DEFAULT 'user' NOT NULL,
                        "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                        "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE "user"
                    ALTER COLUMN id SET NOT NULL,
                    ALTER COLUMN name TYPE TEXT,
                    ALTER COLUMN name SET NOT NULL,
                    ALTER COLUMN email TYPE TEXT
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    UPDATE "user"
                    SET email = id || '@{self.LOCAL_DEV_FALLBACK_EMAIL_DOMAIN}'
                    WHERE email IS NULL
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE "user"
                    ALTER COLUMN email SET NOT NULL
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE "user"
                    ADD COLUMN IF NOT EXISTS "emailVerified" BOOLEAN DEFAULT false NOT NULL,
                    ADD COLUMN IF NOT EXISTS image TEXT,
                    ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user' NOT NULL,
                    ADD COLUMN IF NOT EXISTS "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                    ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    UPDATE "user"
                    SET
                        "emailVerified" = COALESCE("emailVerified", false),
                        role = COALESCE(role, 'user'),
                        "createdAt" = COALESCE("createdAt", now()),
                        "updatedAt" = COALESCE("updatedAt", now())
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE "user"
                    ALTER COLUMN "emailVerified" SET DEFAULT false,
                    ALTER COLUMN "emailVerified" SET NOT NULL,
                    ALTER COLUMN role SET DEFAULT 'user',
                    ALTER COLUMN role SET NOT NULL,
                    ALTER COLUMN "createdAt" SET DEFAULT now(),
                    ALTER COLUMN "createdAt" SET NOT NULL,
                    ALTER COLUMN "updatedAt" SET DEFAULT now(),
                    ALTER COLUMN "updatedAt" SET NOT NULL
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'user_email_unique'
                              AND conrelid = 'user'::regclass
                        ) THEN
                            ALTER TABLE "user"
                            ADD CONSTRAINT "user_email_unique" UNIQUE ("email");
                        END IF;
                    END $$;
                    """
                )
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
        """Expose deterministic local developer credentials for local tooling."""
        return {
            "user_id": cls.LOCAL_DEV_USER_ID,
            "name": cls.LOCAL_DEV_USER_NAME,
            "email": cls.LOCAL_DEV_USER_EMAIL,
            "tier": cls.LOCAL_DEV_TIER,
            "api_key": cls.LOCAL_DEV_API_KEY,
            "credits_balance": cls.LOCAL_DEV_CREDITS_BALANCE,
            "lifetime_billing_micro": cls.LOCAL_DEV_LIFETIME_BILLING_MICRO,
        }

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
        key_hash = hashlib.sha256(self.LOCAL_DEV_API_KEY.encode()).hexdigest()
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
