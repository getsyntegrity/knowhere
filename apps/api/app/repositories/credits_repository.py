"""
Credits 数据访问层
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List

from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user import User
from app.repositories.base_repository import BaseRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class CreditsRepository(BaseRepository[CreditsTransaction, dict, dict]):
    """Credits 数据访问"""
    
    def __init__(self):
        super().__init__(CreditsTransaction)
    
    async def get_by_user_id(self, session: AsyncSession, user_id: str, limit: int = 100, offset: int = 0) -> List[CreditsTransaction]:
        """获取用户的Credits交易记录"""
        result = await session.execute(
            select(CreditsTransaction)
            .where(CreditsTransaction.user_id == user_id)
            .order_by(CreditsTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_by_transaction_type(self, session: AsyncSession, user_id: str, transaction_type: str) -> List[CreditsTransaction]:
        """根据交易类型获取记录"""
        result = await session.execute(
            select(CreditsTransaction)
            .where(CreditsTransaction.user_id == user_id)
            .where(CreditsTransaction.transaction_type == transaction_type)
            .order_by(CreditsTransaction.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_balance(self, session: AsyncSession, user_id: str) -> int:
        """获取用户Credits余额"""
        result = await session.execute(
            select(User.credits_balance)
            .where(User.id == user_id)
        )
        balance = result.scalar_one_or_none()
        return balance or 0
    
    async def cap_balance(self, session: AsyncSession, user_id: str, max_balance: int) -> bool:
        """
        如果用户当前余额高于 max_balance，则将余额调整为 max_balance。
        返回值表示是否发生了更新。
        """
        from sqlalchemy import update
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .where(User.credits_balance > max_balance)
            .values(credits_balance=max_balance)
        )
        await session.commit()
        return result.rowcount > 0
    
    async def add_credits(self, session: AsyncSession, user_id: str, amount: int) -> bool:
        """增加Credits"""
        from sqlalchemy import update
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(credits_balance=User.credits_balance + amount)
        )
        await session.commit()
        return result.rowcount > 0
    
    async def deduct_credits(self, session: AsyncSession, user_id: str, amount: int) -> bool:
        """扣除Credits"""
        from sqlalchemy import and_, update
        result = await session.execute(
            update(User)
            .where(and_(User.id == user_id, User.credits_balance >= amount))
            .values(credits_balance=User.credits_balance - amount)
        )
        await session.commit()
        return result.rowcount > 0
    
    async def get_usage_stats(self, session: AsyncSession, user_id: str, period: str = "month") -> Dict[str, Any]:
        """获取使用统计"""
        # 计算时间范围
        now = datetime.utcnow()
        if period == "day":
            start_date = now - timedelta(days=1)
        elif period == "week":
            start_date = now - timedelta(weeks=1)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
        
        # 查询使用统计
        usage_result = await session.execute(
            select(
                func.sum(CreditsTransaction.credits_amount).label("total_used"),
                func.count(CreditsTransaction.id).label("transaction_count")
            )
            .where(CreditsTransaction.user_id == user_id)
            .where(CreditsTransaction.transaction_type == "usage")
            .where(CreditsTransaction.created_at >= start_date)
        )
        
        usage_stats = usage_result.first()
        
        # 查询购买统计
        purchase_result = await session.execute(
            select(
                func.sum(CreditsTransaction.credits_amount).label("total_purchased"),
                func.count(CreditsTransaction.id).label("purchase_count")
            )
            .where(CreditsTransaction.user_id == user_id)
            .where(CreditsTransaction.transaction_type == "purchase")
            .where(CreditsTransaction.created_at >= start_date)
        )
        
        purchase_stats = purchase_result.first()
        
        return {
            "period": period,
            "total_used": abs(usage_stats.total_used or 0),
            "total_purchased": purchase_stats.total_purchased or 0,
            "transaction_count": usage_stats.transaction_count or 0,
            "purchase_count": purchase_stats.purchase_count or 0,
            "start_date": start_date,
            "end_date": now
        }
    
    async def get_recent_transactions(self, session: AsyncSession, user_id: str, limit: int = 10) -> List[CreditsTransaction]:
        """获取最近的交易记录"""
        result = await session.execute(
            select(CreditsTransaction)
            .where(CreditsTransaction.user_id == user_id)
            .order_by(CreditsTransaction.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_recent_payment_credits(self, session: AsyncSession, user_id: str, days: int) -> int:
        """获取最近 N 天支付获得的总 Credits（仅成功记录，忽略空值）"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await session.execute(
            select(func.coalesce(func.sum(PaymentRecord.credits_amount), 0))
            .where(PaymentRecord.user_id == user_id)
            .where(PaymentRecord.status == "succeeded")
            .where(PaymentRecord.credits_amount.isnot(None))
            .where(PaymentRecord.created_at >= cutoff)
        )
        return result.scalar_one() or 0
