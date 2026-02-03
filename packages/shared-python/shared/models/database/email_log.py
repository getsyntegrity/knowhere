"""
邮件发送日志数据模型
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base

if TYPE_CHECKING:
    pass


class EmailLog(Base):
    """邮件发送日志模型 - 记录邮件发送历史"""
    __tablename__ = "email_logs"
    
    # 主键
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    
    # 关联用户（可选，某些邮件可能不关联用户）
    user_id: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        index=True
    )
    
    # 邮件基本信息
    email_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 邮件类型：welcome, purchase_confirmation, job_completion, job_failure, custom
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # 收件人邮箱
    recipient_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 收件人名称
    
    # 邮件内容
    subject: Mapped[str] = mapped_column(String(512), nullable=False)  # 邮件主题
    template_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Resend模板ID
    template_variables: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # 模板变量
    
    # 发送结果
    success: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)  # 是否成功
    message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Resend返回的邮件ID
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 错误信息（如果失败）
    
    # 关联信息（可选）
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # 关联的任务ID（如果是任务相关邮件）
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 关系
    # 关系
    
    # 索引
    __table_args__ = (
        Index('idx_email_logs_user_id', 'user_id'),
        Index('idx_email_logs_recipient_email', 'recipient_email'),
        Index('idx_email_logs_email_type', 'email_type'),
        Index('idx_email_logs_success', 'success'),
        Index('idx_email_logs_created_at', 'created_at'),
        Index('idx_email_logs_job_id', 'job_id'),
    )
    
    def __repr__(self):
        return f"<EmailLog(id={self.id}, email_type='{self.email_type}', recipient='{self.recipient_email}', success={self.success})>"
    
    def is_successful(self) -> bool:
        """检查是否发送成功"""
        return self.success
    
    def is_failed(self) -> bool:
        """检查是否发送失败"""
        return not self.success

