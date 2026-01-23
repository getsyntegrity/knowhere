"""
计费相关 Schema
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SubscribeRequest(BaseModel):
    """订阅请求"""
    plan_id: str = Field(..., description="订阅计划ID")
    payment_method_id: Optional[str] = Field(default=None, description="支付方式ID")


class BuyCreditsRequest(BaseModel):
    """购买Credits请求"""
    credits_amount: int = Field(..., gt=0, description="购买的Credits数量")
    payment_method_id: Optional[str] = Field(default=None, description="支付方式ID")


class BuyCreditsPackageRequest(BaseModel):
    """通过价格ID购买Credits包请求"""
    price_id: str = Field(..., description="Stripe价格ID")
    quantity: int = Field(default=1, gt=0, description="购买数量")


class CreditsBalanceResponse(BaseModel):
    """Credits余额响应"""
    credits_balance: float
    credits_limit: float
    usage_percentage: float


class UsageStatsResponse(BaseModel):
    """使用统计响应"""
    period: str
    total_credits_used: float
    api_calls_count: int
    success_rate: float
    average_response_time: float
    top_endpoints: List[Dict[str, Any]]


class TransactionHistoryResponse(BaseModel):
    """交易历史响应"""
    id: str
    credits_amount: float
    transaction_type: str
    description: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class PaymentIntentResponse(BaseModel):
    """支付意图响应"""
    client_secret: str
    payment_intent_id: str


class CheckoutSessionResponse(BaseModel):
    """支付会话响应"""
    checkout_url: str
    session_id: str
