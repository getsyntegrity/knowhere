"""
Job数据模型 - 用户API业务任务
"""
from __future__ import annotations

from datetime import datetime

# 前向引用，避免循环导入
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base

if TYPE_CHECKING:
    from shared.models.database.job_result import JobResult
    from shared.models.database.job_state_audit_log import JobStateAuditLog
    from shared.models.database.job_state_history import JobStateHistory
    from shared.models.database.user import User
    from shared.models.database.webhook_log import WebhookLog


class Job(Base):
    """Job模型 - 用户API业务任务"""
    __tablename__ = "jobs"
    
    # 主键
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    
    # 用户关联
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # 任务基本信息
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # kb_management
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # PRD状态: pending, waiting-file, running, converting, done, failed
    
    # 文件信息
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # direct_upload, url
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # 原始文件路径
    s3_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # S3存储键
    
    # Webhook配置
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # 元数据和错误信息
    job_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # JSON存储
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 版本控制（乐观锁）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    # 关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    user: Mapped["User"] = relationship("User", back_populates="jobs", lazy="select")
    state_history: Mapped[list["JobStateHistory"]] = relationship("JobStateHistory", back_populates="job", cascade="all, delete-orphan")
    state_audit_logs: Mapped[list["JobStateAuditLog"]] = relationship("JobStateAuditLog", back_populates="job", cascade="all, delete-orphan")
    webhook_logs: Mapped[list["WebhookLog"]] = relationship("WebhookLog", back_populates="job", cascade="all, delete-orphan")
    job_result: Mapped[Optional["JobResult"]] = relationship("JobResult", back_populates="job", uselist=False, lazy="selectin")
    
    # 索引
    __table_args__ = (
        Index('idx_job_user_id', 'user_id'),
        Index('idx_job_status', 'status'),
        Index('idx_job_type', 'job_type'),
        Index('idx_job_created_at', 'created_at'),
        Index('idx_job_user_status', 'user_id', 'status'),
    )
    
    def __repr__(self):
        return f"<Job(job_id={self.job_id}, type='{self.job_type}', status='{self.status}')>"
    
    def is_terminal_state(self) -> bool:
        """检查是否为终态"""
        return self.status in ['done', 'failed']
    
    def is_processing(self) -> bool:
        """检查是否正在处理中"""
        return self.status == 'running'
