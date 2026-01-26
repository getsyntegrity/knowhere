"""
Webhook相关Schema
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class WebhookConfigCreate(BaseModel):
    """创建Webhook配置请求"""
    webhook_url: HttpUrl = Field(..., description="Webhook URL")
    events: List[str] = Field(default=["job.completed", "job.failed"], description="监听的事件类型")
    enabled: bool = Field(default=True, description="是否启用")


class WebhookConfigResponse(BaseModel):
    """Webhook配置响应"""
    id: str = Field(..., description="配置ID")
    webhook_url: str = Field(..., description="Webhook URL")
    events: List[str] = Field(..., description="监听的事件类型")
    enabled: bool = Field(..., description="是否启用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class WebhookLogResponse(BaseModel):
    """Webhook日志响应"""
    id: str = Field(..., description="日志ID")
    job_id: str = Field(..., description="任务ID")
    webhook_url: str = Field(..., description="Webhook URL")
    attempt_number: int = Field(..., description="尝试次数")
    response_status_code: Optional[int] = Field(None, description="响应状态码")
    response_body: Optional[str] = Field(None, description="响应体")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")


class WebhookLogList(BaseModel):
    """Webhook日志列表"""
    logs: List[WebhookLogResponse] = Field(..., description="日志列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class WebhookStatsResponse(BaseModel):
    """Webhook统计响应"""
    total_attempts: int = Field(..., description="总尝试次数")
    successful_attempts: int = Field(..., description="成功次数")
    failed_attempts: int = Field(..., description="失败次数")
    success_rate: float = Field(..., description="成功率")


class WebhookTestRequest(BaseModel):
    """Webhook测试请求"""
    webhook_url: HttpUrl = Field(..., description="测试的Webhook URL")


class WebhookTestResponse(BaseModel):
    """Webhook测试响应"""
    success: bool = Field(..., description="是否成功")
    status_code: Optional[int] = Field(None, description="响应状态码")
    response_body: Optional[str] = Field(None, description="响应体")
    error_message: Optional[str] = Field(None, description="错误信息")
    test_time: datetime = Field(..., description="测试时间")


class WebhookTriggerRequest(BaseModel):
    """Webhook手动触发请求"""
    job_id: str = Field(..., description="任务ID")


class WebhookTriggerResponse(BaseModel):
    """Webhook手动触发响应"""
    success: bool = Field(..., description="是否成功")
    status_code: Optional[int] = Field(None, description="HTTP状态码")
    response_body: Optional[str] = Field(None, description="响应体")
    duration_ms: int = Field(..., description="耗时(ms)")
    delivery_id: Optional[str] = Field(None, description="投递日志ID")
    error_message: Optional[str] = Field(None, description="错误信息")
