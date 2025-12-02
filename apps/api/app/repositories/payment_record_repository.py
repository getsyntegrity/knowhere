"""
支付记录数据访问层（用于幂等性保证）
"""
from typing import Optional

from shared.models.database.payment_record import PaymentRecord
from app.repositories.base_repository import BaseRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentRecordRepository(BaseRepository[PaymentRecord, dict, dict]):
    """支付记录数据访问"""
    
    def __init__(self):
        super().__init__(PaymentRecord)
    
    async def get_by_payment_intent_id(self, session: AsyncSession, payment_intent_id: str) -> Optional[PaymentRecord]:
        """根据PaymentIntent ID获取支付记录"""
        result = await session.execute(
            select(PaymentRecord)
            .where(PaymentRecord.payment_intent_id == payment_intent_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_checkout_session_id(self, session: AsyncSession, checkout_session_id: str) -> Optional[PaymentRecord]:
        """根据Checkout Session ID获取支付记录"""
        result = await session.execute(
            select(PaymentRecord)
            .where(PaymentRecord.checkout_session_id == checkout_session_id)
        )
        return result.scalar_one_or_none()
    
    async def is_processed(self, session: AsyncSession, payment_intent_id: Optional[str] = None, checkout_session_id: Optional[str] = None) -> bool:
        """检查支付是否已处理（幂等性检查）"""
        if payment_intent_id:
            record = await self.get_by_payment_intent_id(session, payment_intent_id)
            if record and record.is_succeeded():
                return True
        
        if checkout_session_id:
            record = await self.get_by_checkout_session_id(session, checkout_session_id)
            if record and record.is_succeeded():
                return True
        
        return False

