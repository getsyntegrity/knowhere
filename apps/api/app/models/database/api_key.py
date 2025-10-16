"""
API Key 数据模型
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

from app.core.database import Base


class APIKey(Base):
    """API Key 模型"""
    __tablename__ = "api_keys"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # 加密存储
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # API Key 名称
    enabled_modules: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)  # 启用的功能模块
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 过期时间
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否激活
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 最后使用时间
    
    # 关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    user: Mapped[User] = relationship("User", back_populates="api_keys", lazy="select")
    
    def __repr__(self):
        return f"<APIKey(id={self.id}, name='{self.name}', user_id='{self.user_id}')>"
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """检查是否有效"""
        return self.is_active and not self.is_expired()
