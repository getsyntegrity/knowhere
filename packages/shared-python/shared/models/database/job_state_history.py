"""
Job状态历史数据模型
"""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class JobStateHistory(Base):
    """Job状态历史模型 - 记录状态机每次转换"""
    __tablename__ = "job_state_history"
    
    # 主键
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    
    # 关联Job
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    
    # 状态转换信息
    from_state: Mapped[str] = mapped_column(String(50), nullable=False)
    to_state: Mapped[str] = mapped_column(String(50), nullable=False)
    transition_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # JSON存储
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    job: Mapped["Job"] = relationship("Job", back_populates="state_history")
    
    # 索引
    __table_args__ = (
        Index('idx_job_state_history_job_id', 'job_id'),
        Index('idx_job_state_history_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<JobStateHistory(job_id={self.job_id}, {self.from_state}->{self.to_state})>"
