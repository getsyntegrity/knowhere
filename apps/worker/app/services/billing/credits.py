"""
Worker Billing - Simple credits deduction for document processing.
"""
from loguru import logger
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.user import User
from shared.models.database.credits_transaction import CreditsTransaction


async def deduct_credits(
    session: AsyncSession,
    user_id: str, 
    amount: int, 
    description: str
) -> bool:
    """
    Deduct credits from user balance.
    
    Args:
        session: Database session
        user_id: User ID to charge
        amount: Credits to deduct (1 credit = 1 page)
        description: Transaction description
        
    Returns:
        True if successful, False if insufficient balance
    """
    # Check current balance
    balance_result = await session.execute(
        select(User.credits_balance).where(User.id == user_id)
    )
    current_balance = balance_result.scalar_one_or_none() or 0
    
    if current_balance < amount:
        logger.warning(f"Insufficient credits: user={user_id}, balance={current_balance}, required={amount}")
        return False
    
    # Atomic deduct with balance check
    result = await session.execute(
        update(User)
        .where(and_(User.id == user_id, User.credits_balance >= amount))
        .values(credits_balance=User.credits_balance - amount)
    )
    
    if result.rowcount == 0:
        return False
    
    # Record transaction
    transaction = CreditsTransaction(
        user_id=user_id,
        credits_amount=-amount,
        transaction_type="usage",
        description=description
    )
    session.add(transaction)
    
    logger.info(f"Credits deducted: user={user_id}, amount={amount}")
    return True
