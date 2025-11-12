"""
Job状态转换审计日志模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class JobStateAuditLog(Base):
    """Job状态转换审计日志"""
    __tablename__ = "job_state_audit_logs"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 任务关联
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    
    # 状态转换信息
    from_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 源状态
    to_state: Mapped[str] = mapped_column(String(50), nullable=False)  # 目标状态
    transition_reason: Mapped[str] = mapped_column(String(100), nullable=False)  # 转换原因
    
    # 操作者信息
    operator_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # 操作者ID
    operator_type: Mapped[str] = mapped_column(String(20), nullable=False, default="system")  # 操作者类型: system, user, retry
    
    # 转换元数据
    transition_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # 转换时的额外信息
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    job: Mapped["Job"] = relationship("Job", back_populates="state_audit_logs", lazy="select")
    
    # 索引
    __table_args__ = (
        Index('idx_audit_log_job_id', 'job_id'),
        Index('idx_audit_log_created_at', 'created_at'),
        Index('idx_audit_log_job_created', 'job_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<JobStateAuditLog(job_id={self.job_id}, {self.from_state}->{self.to_state})>"
