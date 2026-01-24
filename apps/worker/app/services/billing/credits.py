"""
Worker Billing - Simple credits deduction for document processing.
"""
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.config import settings
from shared.models.database.user import User
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.payment_record import PaymentRecord
from shared.core.billing import MicroDollar


async def deduct_credits(
    session: AsyncSession,
    user_id: str, 
    micro_dollar: MicroDollar, 
    description: str
) -> bool:
    """
    Deduct credits from user balance.
    
    Args:
        session: Database session
        user_id: User ID to charge
        amount: MicroDollar amount to deduct
        description: Transaction description
        
    Returns:
        True if successful, False if insufficient balance
    """
    amount_micros = micro_dollar.amount
    
    # Check current balance
    balance_result = await session.execute(
        select(User.credits_balance).where(User.id == user_id)
    )
    current_balance = balance_result.scalar_one_or_none() or 0
    
    # --- Expiration Check (Sync with API Logic) ---
    try:
        valid_days = getattr(settings, "CREDITS_VALID_DAYS", 90)
        cutoff = datetime.utcnow() - timedelta(days=valid_days)
        
        # Calculate valid credits from payments
        recent_credits_result = await session.execute(
            select(func.coalesce(func.sum(PaymentRecord.credits_amount), 0))
            .where(PaymentRecord.user_id == user_id)
            .where(PaymentRecord.status == "succeeded")
            .where(PaymentRecord.credits_amount.isnot(None))
            .where(PaymentRecord.created_at >= cutoff)
        )
        recent_credits = int(recent_credits_result.scalar_one() or 0)
        
        # If balance exceeds valid credits, expire the excess
        if recent_credits < current_balance:
            expired_amount = current_balance - recent_credits
            logger.info(f"User {user_id} has expired credits (Worker): balance={current_balance}, valid={recent_credits}, expired={expired_amount}")
            
            # Deduct expired amount
            expire_result = await session.execute(
                update(User)
                .where(and_(User.id == user_id, User.credits_balance >= expired_amount))
                .values(credits_balance=User.credits_balance - expired_amount)
            )
            
            if expire_result.rowcount > 0:
                # Record transaction
                exp_trans = CreditsTransaction(
                    user_id=user_id,
                    credits_amount=-expired_amount,
                    transaction_type="expiration",
                    description="Credits expired due to validity period (Worker sync)"
                )
                session.add(exp_trans)
                
                # Update current balance for next check
                current_balance = recent_credits
    except Exception as e:
        logger.error(f"Failed to check credit expiration in worker: {e}")
        # Continue with deduction even if check fails, to avoid blocking user
    # ----------------------------------------------
    
    if current_balance < amount_micros:
        logger.warning(f"Insufficient credits: user={user_id}, balance={current_balance}, required={amount_micros}")
        return False
    
    # Atomic deduct with balance check
    result = await session.execute(
        update(User)
        .where(and_(User.id == user_id, User.credits_balance >= amount_micros))
        .values(credits_balance=User.credits_balance - amount_micros)
    )
    
    if result.rowcount == 0:
        return False
    
    # Record transaction
    transaction = CreditsTransaction(
        user_id=user_id,
        credits_amount=-amount_micros,
        transaction_type="usage",
        description=description
    )
    session.add(transaction)
    
    logger.info(f"Credits deducted: user={user_id}, amount={amount_micros}")
    return True
