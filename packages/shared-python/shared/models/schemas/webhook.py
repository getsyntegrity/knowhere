"""
Webhook Related Schemas
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class WebhookConfigCreate(BaseModel):
    """Create Webhook Configuration Request"""
    webhook_url: HttpUrl = Field(..., description="Webhook URL")
    events: List[str] = Field(default=["job.completed", "job.failed"], description="Events to listen for")
    enabled: bool = Field(default=True, description="Whether enabled")


class WebhookConfigResponse(BaseModel):
    """Webhook Configuration Response"""
    id: str = Field(..., description="Configuration ID")
    webhook_url: str = Field(..., description="Webhook URL")
    events: List[str] = Field(..., description="Events to listen for")
    enabled: bool = Field(..., description="Whether enabled")
    created_at: datetime = Field(..., description="Created time")
    updated_at: datetime = Field(..., description="Updated time")


class WebhookLogResponse(BaseModel):
    """Webhook Log Response"""
    id: str = Field(..., description="Log ID")
    job_id: str = Field(..., description="Job ID")
    webhook_url: str = Field(..., description="Webhook URL")
    attempt_number: int = Field(..., description="Attempt number")
    response_status_code: Optional[int] = Field(None, description="Response status code")
    response_body: Optional[str] = Field(None, description="Response body")
    error_message: Optional[str] = Field(None, description="Error message")
    duration_ms: int = Field(0, description="Request duration in milliseconds")
    created_at: datetime = Field(..., description="Created time")


class WebhookLogList(BaseModel):
    """Webhook Log List"""
    logs: List[WebhookLogResponse] = Field(..., description="Log list")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")


class WebhookStatsResponse(BaseModel):
    """Webhook Statistics Response"""
    total_attempts: int = Field(..., description="Total attempts")
    successful_attempts: int = Field(..., description="Successful attempts")
    failed_attempts: int = Field(..., description="Failed attempts")
    success_rate: float = Field(..., description="Success rate")


class WebhookTestRequest(BaseModel):
    """Webhook Test Request"""
    webhook_url: HttpUrl = Field(..., description="Test Webhook URL")


class WebhookTestResponse(BaseModel):
    """Webhook Test Response"""
    success: bool = Field(..., description="Whether successful")
    status_code: Optional[int] = Field(None, description="Response status code")
    response_body: Optional[str] = Field(None, description="Response body")
    error_message: Optional[str] = Field(None, description="Error message")
    test_time: datetime = Field(..., description="Test time")


class WebhookTriggerRequest(BaseModel):
    """Webhook Manual Trigger Request"""
    job_id: str = Field(..., description="Job ID")


class WebhookTriggerResponse(BaseModel):
    """Webhook Manual Trigger Response"""
    success: bool = Field(..., description="Whether successful")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    response_body: Optional[str] = Field(None, description="Response body")
    duration_ms: int = Field(..., description="Duration (ms)")
    delivery_id: Optional[str] = Field(None, description="Delivery Log ID")
    error_message: Optional[str] = Field(None, description="Error message")
