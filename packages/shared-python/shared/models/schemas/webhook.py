"""
Webhook Schemas

- WebhookLogResponse: Delivery attempt history
- WebhookLogList: Paginated log list
- WebhookTriggerRequest: Manual trigger request
- WebhookTriggerResponse: Manual trigger response
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WebhookLogResponse(BaseModel):
    """Webhook delivery attempt log entry."""
    
    id: str = Field(..., description="Log ID")
    job_id: str = Field(..., description="Job ID")
    webhook_url: str = Field(..., description="Webhook URL")
    attempt_number: int = Field(..., description="Attempt number (1-6)")
    request_payload: dict = Field(..., description="Request payload sent to webhook")
    signature: Optional[str] = Field(None, description="HMAC signature")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key")
    response_status_code: Optional[int] = Field(None, description="HTTP response status code")
    response_body: Optional[str] = Field(None, description="Response body (truncated)")
    error_message: Optional[str] = Field(None, description="Error message if request failed")
    duration_ms: int = Field(0, description="Request duration in milliseconds")
    created_at: datetime = Field(..., description="Timestamp when attempt was made")


class WebhookLogList(BaseModel):
    """Paginated list of webhook delivery logs."""
    
    logs: List[WebhookLogResponse] = Field(..., description="List of log entries")
    total: int = Field(..., description="Total count in this page")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")


class WebhookTriggerRequest(BaseModel):
    """Request to manually trigger a webhook."""
    
    job_id: str = Field(..., description="Job ID to trigger webhook for")


class WebhookTriggerResponse(BaseModel):
    """Response from manual webhook trigger."""
    
    success: bool = Field(..., description="Whether the webhook was delivered successfully")
    status_code: Optional[int] = Field(None, description="HTTP status code from target server")
    response_body: Optional[str] = Field(None, description="Response body from target server")
    duration_ms: int = Field(..., description="Request duration in milliseconds")
    delivery_id: Optional[str] = Field(None, description="Delivery log ID for reference")
    error_message: Optional[str] = Field(None, description="Error message if request failed")
