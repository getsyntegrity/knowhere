from datetime import datetime
from sqlalchemy import Text, BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.database.base import Base

class UserBalance(Base):
    """
    User Balance Model
    Stores user's credit balance and stripe customer ID.
    Replaces reliance on User model for billing data.
    """
    __tablename__ = "user_balances"

    user_id: Mapped[str] = mapped_column(Text, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    credits_balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
