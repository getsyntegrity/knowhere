"""Payment-record repository used for idempotency checks."""

from typing import Optional

from app.repositories.base_repository import BaseRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.payment_record import PaymentRecord


class PaymentRecordRepository(BaseRepository[PaymentRecord, dict, dict]):
    """Payment-record data access."""

    def __init__(self):
        super().__init__(PaymentRecord)

    async def get_by_payment_intent_id(
        self, session: AsyncSession, payment_intent_id: str
    ) -> Optional[PaymentRecord]:
        """Get a payment record by PaymentIntent ID."""
        result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.payment_intent_id == payment_intent_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_checkout_session_id(
        self, session: AsyncSession, checkout_session_id: str
    ) -> Optional[PaymentRecord]:
        """Get a payment record by Checkout Session ID."""
        result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.checkout_session_id == checkout_session_id
            )
        )
        return result.scalar_one_or_none()

    async def is_processed(
        self,
        session: AsyncSession,
        payment_intent_id: Optional[str] = None,
        checkout_session_id: Optional[str] = None,
    ) -> bool:
        """Check whether a payment has already been processed."""
        if payment_intent_id:
            record = await self.get_by_payment_intent_id(session, payment_intent_id)
            if record and record.is_succeeded():
                return True

        if checkout_session_id:
            record = await self.get_by_checkout_session_id(session, checkout_session_id)
            if record and record.is_succeeded():
                return True

        return False
