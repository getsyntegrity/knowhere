"""Dashboard schemas."""
from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class OverviewResponse(BaseModel):
    """Overview response payload."""

    user_info: Dict[str, Any]
    subscription_info: Dict[str, Any]
    credits_info: Dict[str, Any]
    task_stats: Dict[str, Any]
    api_usage_stats: Dict[str, Any]
    knowledge_base_stats: Dict[str, Any]


class UsageAnalyticsResponse(BaseModel):
    """Usage analytics response payload."""

    period: str
    total_api_calls: int
    total_credits_used: int
    success_rate: float
    average_response_time: float
    endpoint_usage: List[Dict[str, Any]]
    daily_usage: List[Dict[str, Any]]


class NotificationResponse(BaseModel):
    """Notification response payload."""

    id: str
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardStatsResponse(BaseModel):
    """Dashboard stats response payload."""

    overview: OverviewResponse
    usage_analytics: UsageAnalyticsResponse
    notifications: List[NotificationResponse]
