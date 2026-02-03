from datetime import datetime
from sqlalchemy import Text, BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from shared.core.database import Base

class UserBalance(Base):
    """
    User Balance Model
    Stores user's credit balance and stripe customer ID.
    Replaces reliance on User model for billing data.
    """
    __tablename__ = "user_balances"

    user_id: Mapped[str] = mapped_column(Text, ForeignKey("user.id", ondelete="RESTRICT"), primary_key=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    credits_balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
