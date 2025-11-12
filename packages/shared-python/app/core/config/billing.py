"""
计费相关配置
"""
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class BillingConfig(BaseSettings):
    """计费配置"""
    
    # Stripe 配置
    STRIPE_SECRET_KEY: Optional[str] = Field(default=None, description="Stripe 密钥")
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(default=None, description="Stripe 公钥")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None, description="Stripe Webhook 密钥")
    
    # 订阅计划配置
    FREE_PLAN_CREDITS: int = Field(default=100, description="免费计划每月Credits")
    PLUS_PLAN_CREDITS: int = Field(default=1000, description="Plus计划每月Credits")
    PRO_PLAN_CREDITS: int = Field(default=10000, description="Pro计划每月Credits")
    
    # Credits 配置
    CREDITS_PER_API_CALL: int = Field(default=1, description="每次API调用消耗的Credits")
    LOW_BALANCE_THRESHOLD: int = Field(default=10, description="低余额预警阈值")
    
    # 订阅计划价格（美分）
    PLUS_PLAN_PRICE: int = Field(default=999, description="Plus计划价格（美分）")
    PRO_PLAN_PRICE: int = Field(default=2999, description="Pro计划价格（美分）")
    
    # Webhook配置
    WEBHOOK_SIGNING_SECRET: str = Field(default="default_webhook_secret", env="WEBHOOK_SIGNING_SECRET")
    
    # Resend邮件配置
    RESEND_API_KEY: str = Field(default="", env="RESEND_API_KEY")
    
    # Moesif配置
    MOESIF_APPLICATION_ID: str = Field(default="", env="MOESIF_APPLICATION_ID")
    
    # PostHog配置
    NEXT_PUBLIC_POSTHOG_KEY: str = Field(default="", env="NEXT_PUBLIC_POSTHOG_KEY")
    NEXT_PUBLIC_POSTHOG_HOST: str = Field(default="https://app.posthog.com", env="NEXT_PUBLIC_POSTHOG_HOST")
    
    # 订阅配置
    FREE_PLAN_INITIAL_CREDITS: int = Field(default=100, env="FREE_PLAN_INITIAL_CREDITS")
    
    # S3配置（新增）
    S3_UPLOADS_BUCKET: str = Field(default="", env="S3_UPLOADS_BUCKET")
    S3_RESULTS_BUCKET: str = Field(default="", env="S3_RESULTS_BUCKET")
    
    def validate_billing_config(self) -> bool:
        """验证计费配置"""
        if self.STRIPE_SECRET_KEY:
            required_stripe_fields = [
                self.STRIPE_SECRET_KEY,
                self.STRIPE_PUBLISHABLE_KEY,
                self.STRIPE_WEBHOOK_SECRET
            ]
            return all(field for field in required_stripe_fields)
        return True  # Stripe 配置是可选的
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
