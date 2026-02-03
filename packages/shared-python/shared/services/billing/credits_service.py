"""
Shared Credits Service - Ledger Pattern Implementation
Used by both API and Worker modules

This service implements the ledger pattern where:
- Transactions (CreditsTransaction) are the source of truth
- UserBalance is a materialized view (cached aggregate)
- All operations are atomic within a transaction
"""
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.billing import MicroDollar
from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import InsufficientCreditsException
from shared.core.logging import logger
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user_balance import UserBalance
from shared.repositories.credits_repository import CreditsRepository


class CreditsService:
    """
    Credits management service implementing ledger pattern.
    
    Core Principle:
    ---------------
    1. Insert transaction record (source of truth)
    2. Recalculate balance from ALL transactions
    3. Update user_balance (materialized view)
    4. All in ONE database transaction
    
    Usage:
    ------
    Both API and Worker modules can use this:
    
    ```python
    credits_service = CreditsService()
    
    async with get_db_context() as session:
        new_balance = await credits_service.deduct_credits(
            session=session,
            user_id="user123",
            amount=1000000,  # 1 microdollar = $1
            reason="Job processing"
        )
        await session.commit()  # Atomic: transaction + balance update
    ```
    """
    
    def __init__(self):
        self.repository = CreditsRepository()
    
    async def ensure_user_initialized(
        self, 
        session: AsyncSession, 
        user_id: str
    ) -> None:
        """
        Initialize new user with default credits if not exists.
        Creates both UserBalance and initial transaction records.
        
        Args:
            session: Database session
            user_id: User ID
        """
        existing_balance = await self.repository.get_user_balance(session, user_id)
        if existing_balance:
            return
        
        # Get initial credits amount
        initial_dollars = getattr(settings, "FREE_PLAN_INITIAL_CREDITS", 5)
       initial_amount = MicroDollar.from_dollars(initial_dollars).amount
        
        # Create balance record
        balance_entry = UserBalance(
            user_id=user_id, 
            credits_balance=initial_amount
        )
        session.add(balance_entry)
        
        # Create initial transaction record
        transaction = CreditsTransaction(
            user_id=user_id,
            credits_amount=initial_amount,
            description="New user registration bonus",
            transaction_type="initial_grant"
        )
        session.add(transaction)
        
        # Create payment record for tracking
        payment = PaymentRecord(
            user_id=user_id,
            payment_type="system_grant",
            amount_cents=0,
            currency="USD",
            status="succeeded",
            credits_amount=initial_amount,
            extra_metadata={"reason": "initial_grant"},
            processed_at=datetime.utcnow()
        )
        session.add(payment)
        await session.flush()
        
        logger.info(f"User initialized: user_id={user_id}, credits={initial_amount}")
    
    async def _apply_transaction_and_update_balance(
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,  # Positive or negative
        transaction_type: str,
        description: str,
        stripe_payment_id: Optional[str] = None,
        transaction_metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Core ledger pattern implementation:
        1. Insert transaction record (source of truth)
        2. Aggregate all transactions to calculate true balance
        3. Update user_balance (materialized view)
        
        All operations in caller's transaction context.
        
        Args:
            session: Database session
            user_id: User ID
            amount: Credit amount (positive for add, negative for deduct)
            transaction_type: Type of transaction
            description: Human-readable description
            stripe_payment_id: Optional Stripe payment ID
            transaction_metadata: Optional metadata dict
            
        Returns:
            New balance after operation
        """
        # Step 1: Insert transaction record (ledger entry)
        transaction = CreditsTransaction(
            user_id=user_id,
            credits_amount=amount,
            transaction_type=transaction_type,
            description=description,
            stripe_payment_id=stripe_payment_id,
            transaction_metadata=transaction_metadata
        )
        await self.repository.create_transaction(session, transaction)
        
        # Step 2: Recalculate balance from ledger (source of truth)
        new_balance = await self.repository.recalculate_balance_from_ledger(
            session, user_id
        )
        
        # Step 3: Update materialized view
        await self.repository.update_balance(session, user_id, new_balance)
        
        logger.debug(
            f"Credits updated: user_id={user_id}, amount={amount}, "
            f"new_balance={new_balance}, type={transaction_type}"
        )
        
        return new_balance
    
    async def get_balance(self, session: AsyncSession, user_id: str) -> int:
        """
        Get current balance (fast read from materialized view).
        
        Args:
            session: Database session
            user_id: User ID
            
        Returns:
            Current credits balance
        """
        await self.ensure_user_initialized(session, user_id)
        return await self.repository.get_balance(session, user_id)
    
    async def add_credits(
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,
        reason: str,
        stripe_payment_id: Optional[str] = None,
        transaction_type: str = "purchase",
        transaction_metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Add credits using ledger pattern.
        
        Args:
            session: Database session
            user_id: User ID
            amount: Credits to add (positive)
            reason: Description of why credits added
            stripe_payment_id: Optional Stripe payment ID
            transaction_type: Type of transaction (purchase, bonus, refund, etc.)
            transaction_metadata: Optional metadata
            
        Returns:
            New balance after addition
        """
        await self.ensure_user_initialized(session, user_id)
        
        new_balance = await self._apply_transaction_and_update_balance(
            session=session,
            user_id=user_id,
            amount=amount,  # Positive
            transaction_type=transaction_type,
            description=reason,
            stripe_payment_id=stripe_payment_id,
            transaction_metadata=transaction_metadata
        )
        
        logger.info(
            f"Credits added: user_id={user_id}, amount={amount}, "
            f"new_balance={new_balance}, type={transaction_type}"
        )
        
        return new_balance
    
    async def deduct_credits(
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,
        reason: str,
        api_key_id: Optional[str] = None
    ) -> int:
        """
        Deduct credits using ledger pattern.
        Raises InsufficientCreditsException if balance too low.
        
        Args:
            session: Database session
            user_id: User ID
            amount: Credits to deduct (positive number)
            reason: Description of why credits deducted
            api_key_id: Optional API key ID for tracking
            
        Returns:
            New balance after deduction
            
        Raises:
            InsufficientCreditsException: If insufficient credits
        """
        # Check current balance (read from materialized view)
        current_balance = await self.get_balance(session, user_id)
        if current_balance < amount:
            raise InsufficientCreditsException(
                user_message=f"Insufficient credits. Required: {amount}, Available: {current_balance}",
                required_credits=amount,
                internal_message=f"User {user_id} has insufficient credits: {current_balance} < {amount}"
            )
        
        # Apply ledger entry (negative amount)
        new_balance = await self._apply_transaction_and_update_balance(
            session=session,
            user_id=user_id,
            amount=-amount,  # Negative!
            transaction_type="usage",
            description=reason,
            transaction_metadata={"api_key_id": api_key_id} if api_key_id else None
        )
        
        logger.info(
            f"Credits deducted: user_id={user_id}, amount={amount}, "
            f"new_balance={new_balance}"
        )
        
        return new_balance
    
    async def refund_job_credits(
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,
        job_id: str,
        reason: str = "Job execution failed"
    ) -> int:
        """
        Refund credits for a job (idempotent: same job_id only refunded once).
        
        Args:
            session: Database session
            user_id: User ID
            amount: Credits to refund
            job_id: Job ID (used for idempotency)
            reason: Refund reason
            
        Returns:
            New balance after refund
            
        Raises:
            ValueError: If job already refunded
        """
        from sqlalchemy import select, func
        
        # Check if already refunded
        stmt = select(CreditsTransaction).where(
            CreditsTransaction.user_id == user_id,
            CreditsTransaction.transaction_type == "refund",
            func.json_extract_path_text(
                CreditsTransaction.transaction_metadata, 'job_id'
            ) == job_id
        )
        
        result = await session.execute(stmt)
        existing = result.first()
        
        if existing:
            logger.info(f"Job {job_id} already refunded, skipping")
            raise ValueError(f"Job {job_id} already refunded")
        
        # Execute refund
        new_balance = await self.add_credits(
            session=session,
            user_id=user_id,
            amount=amount,
            reason=reason,
            transaction_type="refund",
            transaction_metadata={"job_id": job_id}
        )
        
        logger.info(f"Job refunded: job_id={job_id}, amount={amount}, new_balance={new_balance}")
        return new_balance
    
    async def expire_old_credits(
        self,
        session: AsyncSession,
        user_id: str,
        valid_days: int = 90
    ) -> int:
        """
        Expire credits older than valid_days.
        Should be called by scheduled job, not on every balance check.
        
        Args:
            session: Database session
            user_id: User ID
            valid_days: Credits validity period in days
            
        Returns:
            Amount expired (0 if nothing expired)
        """
        current_balance = await self.get_balance(session, user_id)
        recent_credits = await self.repository.get_recent_payment_credits(
            session, user_id, valid_days
        )
        
        if recent_credits < current_balance:
            expired_amount = current_balance - recent_credits
            
            # Use ledger pattern to record expiration
            await self._apply_transaction_and_update_balance(
                session=session,
                user_id=user_id,
                amount=-expired_amount,  # Negative
                transaction_type="expiration",
                description=f"Credits expired (>{valid_days} days old)"
            )
            
            logger.info(
                f"Credits expired: user_id={user_id}, amount={expired_amount}, "
                f"remaining={recent_credits}"
            )
            
            return expired_amount
        
        return 0
    
    async def get_usage_stats(
        self,
        session: AsyncSession,
        user_id: str,
        period: str = "month"
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a user.
        
        Args:
            session: Database session
            user_id: User ID
            period: Time period ("month", "week", "all_time")
            
        Returns:
            Dict with usage stats
        """
        from datetime import datetime, timedelta
        from sqlalchemy import select, func
        
        # Calculate time range
        if period == "month":
            start_time = datetime.utcnow() - timedelta(days=30)
        elif period == "week":
            start_time = datetime.utcnow() - timedelta(days=7)
        else:  # all_time
            start_time = None
        
        # Build query
        query = select(
            func.coalesce(func.sum(CreditsTransaction.credits_amount), 0).label("total_used"),
            func.count(CreditsTransaction.id).label("transaction_count")
        ).where(CreditsTransaction.user_id == user_id)
        
        # Only count usage transactions (negative amounts)
        query = query.where(CreditsTransaction.transaction_type == "usage")
        
        if start_time:
            query = query.where(CreditsTransaction.created_at >= start_time)
        
        result = await session.execute(query)
        stats = result.first()
        
        return {
            "period": period,
            "total_used": int(abs(stats.total_used or 0)),
            "transaction_count": int(stats.transaction_count or 0),
            "avg_response_time": 0.0  # TODO: Calculate from usage logs if needed
        }
    
    async def get_transaction_history(
        self,
        session: AsyncSession,
        user_id: str,
        limit: int = 50
    ) -> list:
        """
        Get transaction history for a user.
        
        Args:
            session: Database session
            user_id: User ID
            limit: Maximum number of transactions to return
            
        Returns:
            List of CreditsTransaction records
        """
        from sqlalchemy import select
        
        result = await session.execute(
            select(CreditsTransaction)
            .where(CreditsTransaction.user_id == user_id)
            .order_by(CreditsTransaction.created_at.desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
