"""
User Model - For SQLAlchemy Foreign Key Reference Only.
Note: User data is actually managed by the Dashboard. This model is only used for maintaining database integrity references.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.database import Base


class User(Base):
    """User Model (Reference Only)"""
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # The dashboard owns the full user schema, but guest registration still
    # needs to satisfy the shared NOT NULL display-name constraint.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name={self.name}, email={self.email})>"
