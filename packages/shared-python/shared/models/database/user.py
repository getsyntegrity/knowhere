"""
User Model - For SQLAlchemy Foreign Key Reference Only.
Note: User data is actually managed by the Dashboard. This model is only used for maintaining database integrity references.
"""
from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.database import Base


class User(Base):
    """User Model (Reference Only)"""
    __tablename__ = "user"
    
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    
    def __repr__(self):
        return f"<User(id={self.id})>"
