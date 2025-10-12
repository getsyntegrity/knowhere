"""
OAuth 提供商数据模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID, uuid4

from app.core.database import Base


class OAuthProvider(Base):
    """OAuth 提供商模型"""
    __tablename__ = "oauth_providers"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # google, github, apple
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    # user: Mapped["User"] = relationship("User", back_populates="oauth_providers")  # 暂时注释掉避免循环导入
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('provider', 'provider_user_id', name='uk_provider_user'),
    )
    
    def __repr__(self):
        return f"<OAuthProvider(id={self.id}, provider='{self.provider}', user_id='{self.user_id}')>"
    
    def is_token_expired(self) -> bool:
        """检查访问令牌是否过期"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def needs_refresh(self) -> bool:
        """检查是否需要刷新令牌"""
        return self.refresh_token is not None and self.is_token_expired()
