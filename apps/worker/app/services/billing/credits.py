"""
Worker Billing - Simple credits deduction for document processing.
"""
from loguru import logger
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.user import User
from shared.models.database.credits_transaction import CreditsTransaction
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
