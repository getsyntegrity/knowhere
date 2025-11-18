"""
消息契约Schema定义
用于API服务和Worker服务之间的消息通信
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BaseMessage(BaseModel):
    """消息基类"""
    job_id: str = Field(..., description="任务ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="消息时间戳")
    message_type: str = Field(..., description="消息类型")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class JobStatusUpdateMessage(BaseMessage):
    """Job状态更新消息"""
    message_type: str = Field(default="job_status_update", description="消息类型")
    status: str = Field(..., description="新状态")
    previous_status: Optional[str] = Field(None, description="之前的状态")
    trigger: str = Field(..., description="状态转换触发原因")
    operator_id: Optional[str] = Field(None, description="操作者ID")
    operator_type: str = Field(default="system", description="操作者类型: system/user")
    metadata: Optional[Dict[str, Any]] = Field(None, description="状态转换元数据")


class JobProgressUpdateMessage(BaseMessage):
    """Job进度更新消息"""
    message_type: str = Field(default="job_progress_update", description="消息类型")
    progress: int = Field(..., ge=0, le=100, description="进度百分比 (0-100)")
    message: str = Field(default="", description="进度消息文本")
    metadata: Optional[Dict[str, Any]] = Field(None, description="进度元数据")


class JobResultMessage(BaseMessage):
    """Job结果数据消息"""
    message_type: str = Field(default="job_result", description="消息类型")
    status: str = Field(default="success", description="处理状态")
    
    # Chunks数据（通过job_id引用，API服务从Redis读取）
    chunks_job_id: str = Field(..., description="Chunks数据关联的job_id（用于从Redis读取）")
    
    # 知识库数据
    kb_records: Optional[List[Dict[str, Any]]] = Field(None, description="知识库记录列表")
    
    # 结果文件信息
    result_s3_key: str = Field(..., description="结果ZIP包的S3键")
    checksum: str = Field(..., description="文件校验和")
    statistics: Optional[Dict[str, Any]] = Field(None, description="统计信息")
    zip_size: int = Field(..., description="ZIP文件大小（字节）")
    
    # 存储统计
    stored_count: int = Field(default=0, description="存储的记录数量")
    delivery_mode: str = Field(default="url", description="交付模式")
    
    # 处理结果目录（可选，用于调试）
    add_dir: Optional[str] = Field(None, description="处理结果目录路径")


class JobFailureMessage(BaseMessage):
    """Job失败消息"""
    message_type: str = Field(default="job_failure", description="消息类型")
    error_message: str = Field(..., description="错误消息")
    error_type: Optional[str] = Field(None, description="错误类型")
    stack_trace: Optional[str] = Field(None, description="堆栈跟踪")
    metadata: Optional[Dict[str, Any]] = Field(None, description="错误元数据")

