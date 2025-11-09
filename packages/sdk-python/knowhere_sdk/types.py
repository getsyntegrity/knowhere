"""
类型定义
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime


class KnowhereClientConfig(BaseModel):
    """客户端配置"""
    api_key: str
    base_url: str = "https://api.knowhere.ai"
    headers: Optional[Dict[str, str]] = None
    timeout: int = 30


class ApiResponse(BaseModel):
    """API响应"""
    success: bool
    data: Any
    error: Optional[Dict[str, Any]] = None


class ApiError(Exception):
    """API错误"""
    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details
        super().__init__(message)


# 知识库相关类型
class KBJobCreate(BaseModel):
    """知识库任务创建请求"""
    file_url: str
    webhook_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KBJobResponse(BaseModel):
    """知识库任务响应"""
    job_id: str
    status: str
    current_state: str
    created_at: datetime
    file_url: str
    webhook_url: Optional[str] = None


class KBJobStatus(BaseModel):
    """知识库任务状态"""
    job_id: str
    status: str
    current_state: str
    progress: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    file_url: str
    webhook_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    processing_stats: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


# Webhook相关类型
class WebhookConfig(BaseModel):
    """Webhook配置"""
    webhook_id: str
    webhook_url: str
    events: List[str]
    secret: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WebhookLogResponse(BaseModel):
    """Webhook日志响应"""
    log_id: str
    job_id: str
    event_type: str
    webhook_url: str
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    retry_count: int
    created_at: datetime
    last_attempt_at: datetime


# 任务管理相关类型
class JobStatusResponse(BaseModel):
    """任务状态响应"""
    job_id: str
    job_type: str
    status: str
    current_state: str
    progress: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    file_url: str
    webhook_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class JobResultResponse(BaseModel):
    """任务结果响应"""
    job_id: str
    job_type: str
    status: str
    delivery_mode: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    download_url: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None
    processing_stats: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
