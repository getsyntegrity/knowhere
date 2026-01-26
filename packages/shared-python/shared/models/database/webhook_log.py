"""
Webhook日志数据模型 (Webhook Delivery History)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base

if TYPE_CHECKING:
    from shared.models.database.job import Job
    from shared.models.database.webhook import WebhookEvent


class WebhookLog(Base):
    """Webhook日志模型 - 记录Webhook推送历史"""
    __tablename__ = "webhook_logs"
    
    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    
    # Associations
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=True)  # Optional for backward compatibility
    
    # Webhook信息
    webhook_url: Mapped[str] = mapped_column(String(512), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 第几次尝试（1-5）
    
    # 请求信息
    request_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # JSON存储
    signature: Mapped[str] = mapped_column(String(128), nullable=False)  # HMAC签名
    idempotency_key: Mapped[str] = mapped_column(String(36), nullable=False)  # UUID幂等键
    
    # Response information
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Request duration in milliseconds
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="webhook_logs")
    event: Mapped[Optional["WebhookEvent"]] = relationship("WebhookEvent", back_populates="deliveries", foreign_keys=[event_id])
    
    # Indexes
    __table_args__ = (
        Index('idx_webhook_logs_job_id', 'job_id'),
        Index('idx_webhook_logs_event_id', 'event_id'),
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
