"""Billing configuration."""
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BillingConfig(BaseSettings):
    """Billing configuration."""

    # Stripe configuration.
    STRIPE_SECRET_KEY: Optional[str] = Field(default=None, description="Stripe secret key")
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(default=None, description="Stripe publishable key")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None, description="Stripe webhook secret")

    # Subscription plan configuration.
    FREE_PLAN_CREDITS: int = Field(default=100, description="Monthly credits for the free plan")
    PLUS_PLAN_CREDITS: int = Field(default=1000, description="Monthly credits for the Plus plan")
    PRO_PLAN_CREDITS: int = Field(default=10000, description="Monthly credits for the Pro plan")

    # Credits (Micro-Dollar System: $1.00 = 1,000,000 micro-credits)
    MICRO_DOLLARS_PER_PAGE: int = Field(
        default=1500, 
        description="Micro dollars per page ($0.0015 = 1500 micros)"
    )
    LOW_BALANCE_THRESHOLD: int = Field(default=10_000_000, description="low micro dollars threshold, 10 credits")
    CREDITS_VALID_DAYS: int = Field(default=365, description="Credit validity period in days")

    # Subscription prices in cents.
    PLUS_PLAN_PRICE: int = Field(default=999, description="Plus plan price in cents")
    PRO_PLAN_PRICE: int = Field(default=2999, description="Pro plan price in cents")

    # Webhook configuration.
    WEBHOOK_SIGNING_SECRET: str = Field(default="default_webhook_secret")

    # Resend email configuration.
    RESEND_API_KEY: str = Field(default="")
    RESEND_FROM_EMAIL: str = Field(default="noreply@knowhere.ai", description="Sender email address")
    RESEND_FROM_NAME: str = Field(default="Knowhere AI", description="Sender display name")
    RESEND_MAX_RETRIES: int = Field(default=3, description="Maximum retry count")
    RESEND_RETRY_DELAY: float = Field(default=1.0, description="Retry delay in seconds")
    # Resend template identifiers from the Resend dashboard.
    RESEND_TEMPLATE_WELCOME: Optional[str] = Field(default=None, description="Welcome email template ID")
    RESEND_TEMPLATE_PURCHASE_CONFIRMATION: Optional[str] = Field(default=None, description="Purchase-confirmation email template ID")
    RESEND_TEMPLATE_JOB_COMPLETION: Optional[str] = Field(default=None, description="Job-completion email template ID")
    RESEND_TEMPLATE_JOB_FAILURE: Optional[str] = Field(default=None, description="Job-failure email template ID")
    # Resend template feature toggles.
    RESEND_TEMPLATE_WELCOME_ENABLED: bool = Field(default=False, description="Enable the welcome email template")
    RESEND_TEMPLATE_PURCHASE_CONFIRMATION_ENABLED: bool = Field(default=False, description="Enable the purchase-confirmation email template")
    RESEND_TEMPLATE_JOB_COMPLETION_ENABLED: bool = Field(default=False, description="Enable the job-completion email template")
    RESEND_TEMPLATE_JOB_FAILURE_ENABLED: bool = Field(default=False, description="Enable the job-failure email template")

    # Moesif configuration.
    MOESIF_APPLICATION_ID: str = Field(default="")

    # PostHog configuration.
    NEXT_PUBLIC_POSTHOG_KEY: str = Field(default="")
    NEXT_PUBLIC_POSTHOG_HOST: str = Field(default="https://app.posthog.com")

    # Subscription defaults.
    FREE_PLAN_INITIAL_CREDITS: int = Field(default=5)

    # S3 result-bucket configuration.
    S3_UPLOADS_BUCKET: str = Field(default="")
    S3_RESULTS_BUCKET: str = Field(default="")

    # Frontend callback URL used by Stripe Checkout.
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend URL for Stripe Checkout success/cancel callbacks")

    def validate_billing_config(self) -> bool:
        """Validate the optional billing configuration."""
        if self.STRIPE_SECRET_KEY:
            required_stripe_fields = [
                self.STRIPE_SECRET_KEY,
                self.STRIPE_PUBLISHABLE_KEY,
                self.STRIPE_WEBHOOK_SECRET
            ]
            return all(field for field in required_stripe_fields)
        return True  # Stripe is optional in local or limited-feature setups.

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
