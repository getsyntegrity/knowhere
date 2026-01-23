"""
API 使用日志数据模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class UsageLog(Base):
    """API 使用日志模型"""
    __tablename__ = "usage_logs"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    api_key_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=1, nullable=False) # micro dollars
    response_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 毫秒
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 关系
    # 关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    user: Mapped[User] = relationship("User", back_populates="usage_logs", lazy="select")
    # api_key: Mapped[Optional["APIKey"]] = relationship("APIKey", back_populates="usage_logs")  # 暂时注释掉避免循环导入
    
    def __repr__(self):
        return f"<UsageLog(id={self.id}, endpoint='{self.endpoint}', credits_used={self.credits_used})>"
    
    def is_successful(self) -> bool:
        """检查请求是否成功"""
        return self.status_code is not None and 200 <= self.status_code < 300
    
    def is_error(self) -> bool:
        """检查请求是否出错"""
        return self.status_code is not None and self.status_code >= 400
