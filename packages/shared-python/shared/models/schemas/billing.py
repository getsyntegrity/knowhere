"""Billing schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SubscribeRequest(BaseModel):
    """Request payload for creating or updating a subscription."""

    plan_id: str = Field(..., description="Subscription plan ID")
    payment_method_id: Optional[str] = Field(default=None, description="Payment method ID")


class BuyCreditsRequest(BaseModel):
    """Request payload for purchasing credits directly."""

    credits_amount: int = Field(..., gt=0, description="Credits amount to purchase")
    payment_method_id: Optional[str] = Field(default=None, description="Payment method ID")


class BuyCreditsPackageRequest(BaseModel):
    """Request payload for purchasing a credits package by price ID."""

    price_id: str = Field(..., description="Stripe price ID")
    quantity: int = Field(default=1, gt=0, description="Quantity to purchase")


class CreditsBalanceResponse(BaseModel):
    """Credits-balance response."""

    credits_balance: float


class UsageStatsResponse(BaseModel):
    """Usage-statistics response."""

    period: str
    total_credits_used: float
    api_calls_count: int
    success_rate: float
    average_response_time: float
    top_endpoints: List[Dict[str, Any]]


class TransactionHistoryResponse(BaseModel):
    """Transaction-history response."""

    id: str
    credits_amount: float
    transaction_type: str
    description: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PaymentIntentResponse(BaseModel):
    """Payment-intent response."""

    client_secret: str
    payment_intent_id: str


class CheckoutSessionResponse(BaseModel):
    """Checkout-session response."""

    checkout_url: str
    session_id: str
