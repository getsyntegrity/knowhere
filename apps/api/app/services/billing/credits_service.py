"""
Credits 管理服务
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from shared.core.config import settings
from shared.core.logging import logger
from shared.core.exceptions.DomainExceptions import KnowhereException, WorkerHandlingException
from app.repositories.credits_repository import CreditsRepository
from sqlalchemy.ext.asyncio import AsyncSession


class CreditsService:
    """Credits管理服务"""
    
    def __init__(self):
        self.repository = CreditsRepository()
    
    async def check_balance(self, session: AsyncSession, user_id: str) -> int:
        """
        检查Credits余额：
        - 基于用户当前余额
        - 限制为最近 N 天（env: CREDITS_VALID_DAYS，默认90天）内支付获得的额度上限
        - 如果余额超过有效期内额度，会下调并同步更新到数据库
        """
        user_balance = await self.repository.get_balance(session, user_id)
        valid_days = getattr(settings, "CREDITS_VALID_DAYS", 90)
        recent_credits = await self.repository.get_recent_payment_credits(session, user_id, valid_days)
        
        # 余额不能超过有效期内购入的总额度，过期额度视为失效
        if recent_credits < user_balance:
            await self.repository.cap_balance(session, user_id, recent_credits)
            return recent_credits
        
        return user_balance
    
    async def get_balance(self, session: AsyncSession, user_id: str) -> int:
        """获取Credits余额（check_balance的别名）"""
        return await self.check_balance(session, user_id)
    
    async def deduct_credits(
        self, 
        session: AsyncSession,
        user_id: str, 
        amount: int, 
        reason: str,
        api_key_id: Optional[str] = None
    ) -> bool:
        """扣除Credits"""
        # 1. 检查余额
        current_balance = await self.check_balance(session, user_id)
        if current_balance < amount:
            return False
        
        # 2. 扣除Credits
        success = await self.repository.deduct_credits(session, user_id, amount)
        
        if success:
            # 3. 记录交易
            from shared.models.database.credits_transaction import \
                CreditsTransaction
            transaction = CreditsTransaction(
                user_id=user_id,
                credits_amount=-amount,
                transaction_type="usage",
                description=reason,
                transaction_metadata={"api_key_id": api_key_id} if api_key_id else None
            )
            await self.repository.create(session, transaction)
            
            # 4. 检查余额预警
            new_balance = current_balance - amount
            if new_balance < settings.LOW_BALANCE_THRESHOLD:
                await self._send_low_balance_alert(session, user_id, new_balance)
        
        return success
    
    async def add_credits(
        self, 
        session: AsyncSession,
        user_id: str, 
        amount: int, 
        reason: str,
        stripe_payment_id: Optional[str] = None,
        transaction_type: str = "purchase",
        transaction_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """增加Credits"""
        # 1. 增加Credits
        success = await self.repository.add_credits(session, user_id, amount)
        
        if success:
            # 2. 记录交易
            from shared.models.database.credits_transaction import \
                CreditsTransaction
            transaction = CreditsTransaction(
                user_id=user_id,
                credits_amount=amount,
                transaction_type=transaction_type,
                description=reason,
                stripe_payment_id=stripe_payment_id,
                transaction_metadata=transaction_metadata
            )
            await self.repository.create(session, transaction)
            
            # 3. 发送通知
            await self._send_credits_added_notification(session, user_id, amount)
        
        return success

    async def refund_job_credits(
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,
        job_id: str,
        reason: str = "Job execution failed"
    ) -> bool:
        """
        退还Job Credits（幂等：同一个job_id只退一次）
        """
        from shared.models.database.credits_transaction import CreditsTransaction
        from sqlalchemy import select, func, String
        
        # 检查是否已经退款
        # 使用 func.json_extract_path_text 提取 job_id (兼容 PostgreSQL)
        stmt = select(CreditsTransaction).where(
            CreditsTransaction.user_id == user_id,
            CreditsTransaction.transaction_type == "refund",
            func.json_extract_path_text(CreditsTransaction.transaction_metadata, 'job_id') == job_id
        )
        
        result = await session.execute(stmt)
        existing = result.first()
        
        if existing:
            logger.info(f"Job {job_id} 已经退还过Credits，跳过")
            return False
            
        # 执行退款
        return await self.add_credits(
            session=session,
            user_id=user_id,
            amount=amount,
            reason=reason,
            transaction_type="refund",
            transaction_metadata={"job_id": job_id}
        )
    
    async def get_usage_stats(
        self, 
        session: AsyncSession,
        user_id: str, 
        period: str = "month"
    ) -> Dict[str, Any]:
        """获取使用统计"""
        return await self.repository.get_usage_stats(session, user_id, period)
    
    async def get_transaction_history(
        self, 
        session: AsyncSession,
        user_id: str, 
        limit: int = 50
    ) -> list:
        """获取交易历史"""
        return await self.repository.get_recent_transactions(session, user_id, limit)
    
    async def get_user_transactions(
        self, 
        session: AsyncSession, 
        user_id: str, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[dict]:
        """获取用户Credits交易记录"""
        try:
            transactions = await self.repository.get_by_user_id(session, user_id, limit, offset)
            
            result = []
            for transaction in transactions:
                result.append({
                    "id": transaction.id,
                    "credits_amount": transaction.credits_amount,
                    "transaction_type": transaction.transaction_type,
                    "description": transaction.description,
                    "stripe_payment_id": transaction.stripe_payment_id,
                    "created_at": transaction.created_at,
                    "transaction_metadata": transaction.transaction_metadata
                })
            
            return result
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"获取用户交易记录失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"获取用户交易记录失败: {str(e)}",
                original_exception=e
            )
    
    async def allocate_free_credits(self, session: AsyncSession, user_id: str, user_type: str = "user") -> bool:
        """分配免费Credits"""
        credits_map = {
            "user": 100,
            "admin": 1000,
            "superuser": 10000
        }
        
        amount = credits_map.get(user_type, 100)
        return await self.add_credits(
            session, 
            user_id, 
            amount, 
            f"新用户免费Credits ({user_type})"
        )
    
    async def _send_low_balance_alert(self, session: AsyncSession, user_id: str, balance: int):
        """发送余额不足提醒"""
        # TODO: 实现邮件或推送通知
        print(f"用户 {user_id} Credits余额不足: {balance}")
    
    async def _send_credits_added_notification(self, session: AsyncSession, user_id: str, amount: int):
        """发送Credits增加通知"""
        # TODO: 实现邮件或推送通知
        print(f"用户 {user_id} 获得 {amount} Credits")
