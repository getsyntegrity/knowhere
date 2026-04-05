"""
User Model - For SQLAlchemy Foreign Key Reference Only.
Note: User data is actually managed by the Dashboard. This model is only used for maintaining database integrity references.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.database import Base


class User(Base):
    """User Model (Reference Only)"""
    __tablename__ = "user"
    
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"

