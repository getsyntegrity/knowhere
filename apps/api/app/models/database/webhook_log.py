"""
Webhook日志数据模型
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID, uuid4

from app.core.database import Base


class WebhookLog(Base):
    """Webhook日志模型 - 记录Webhook推送历史"""
    __tablename__ = "webhook_logs"
    
    # 主键
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    
    # 关联Job
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    
    # Webhook信息
    webhook_url: Mapped[str] = mapped_column(String(512), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 第几次尝试（1-5）
    
    # 请求信息
    request_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # JSON存储
    signature: Mapped[str] = mapped_column(String(128), nullable=False)  # HMAC签名
    idempotency_key: Mapped[str] = mapped_column(String(36), nullable=False)  # UUID幂等键
    
    # 响应信息
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    job: Mapped["Job"] = relationship("Job", back_populates="webhook_logs")
    
    # 索引
    __table_args__ = (
        Index('idx_webhook_logs_job_id', 'job_id'),
        Index('idx_webhook_logs_created_at', 'created_at'),
        Index('idx_webhook_logs_attempt', 'job_id', 'attempt_number'),
    )
    
    def __repr__(self):
        return f"<WebhookLog(job_id={self.job_id}, attempt={self.attempt_number}, status={self.response_status_code})>"
    
    def is_success(self) -> bool:
        """检查是否成功"""
        return self.response_status_code is not None and 200 <= self.response_status_code < 300
    
    def is_failed(self) -> bool:
        """检查是否失败"""
        return self.response_status_code is None or self.response_status_code >= 400
