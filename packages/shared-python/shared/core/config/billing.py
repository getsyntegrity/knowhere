"""
计费相关配置
"""
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings
from sqlalchemy.sql.expression import false


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
    CREDITS_PER_PAGE: int = Field(default=1, description="credits per page usage", env="CREDITS_PER_PAGE")
    LOW_BALANCE_THRESHOLD: int = Field(default=10, description="低余额预警阈值")
    CREDITS_VALID_DAYS: int = Field(default=90, env="CREDITS_VALID_DAYS", description="Credits有效期（天），过期点数失效")
    
    # 订阅计划价格（美分）
    PLUS_PLAN_PRICE: int = Field(default=999, description="Plus计划价格（美分）")
    PRO_PLAN_PRICE: int = Field(default=2999, description="Pro计划价格（美分）")
    
    # Webhook配置
    WEBHOOK_SIGNING_SECRET: str = Field(default="default_webhook_secret", env="WEBHOOK_SIGNING_SECRET")
    
    # Resend邮件配置
    RESEND_API_KEY: str = Field(default="", env="RESEND_API_KEY")
    RESEND_FROM_EMAIL: str = Field(default="noreply@knowhere.ai", env="RESEND_FROM_EMAIL", description="发件人邮箱")
    RESEND_FROM_NAME: str = Field(default="Knowhere AI", env="RESEND_FROM_NAME", description="发件人名称")
    RESEND_MAX_RETRIES: int = Field(default=3, env="RESEND_MAX_RETRIES", description="最大重试次数")
    RESEND_RETRY_DELAY: float = Field(default=1.0, env="RESEND_RETRY_DELAY", description="重试延迟秒数")
    # Resend模板ID配置（使用Resend控制台的模板）
    RESEND_TEMPLATE_WELCOME: Optional[str] = Field(default=None, env="RESEND_TEMPLATE_WELCOME", description="欢迎邮件模板ID")
    RESEND_TEMPLATE_PURCHASE_CONFIRMATION: Optional[str] = Field(default=None, env="RESEND_TEMPLATE_PURCHASE_CONFIRMATION", description="购买确认邮件模板ID")
    RESEND_TEMPLATE_JOB_COMPLETION: Optional[str] = Field(default=None, env="RESEND_TEMPLATE_JOB_COMPLETION", description="任务完成邮件模板ID")
    RESEND_TEMPLATE_JOB_FAILURE: Optional[str] = Field(default=None, env="RESEND_TEMPLATE_JOB_FAILURE", description="任务失败邮件模板ID")
    # Resend模板开关配置
    RESEND_TEMPLATE_WELCOME_ENABLED: bool = Field(default=False, env="RESEND_TEMPLATE_WELCOME_ENABLED", description="欢迎邮件模板开关")
    RESEND_TEMPLATE_PURCHASE_CONFIRMATION_ENABLED: bool = Field(default=False, env="RESEND_TEMPLATE_PURCHASE_CONFIRMATION_ENABLED", description="购买确认邮件模板开关")
    RESEND_TEMPLATE_JOB_COMPLETION_ENABLED: bool = Field(default=False, env="RESEND_TEMPLATE_JOB_COMPLETION_ENABLED", description="任务完成邮件模板开关")
    RESEND_TEMPLATE_JOB_FAILURE_ENABLED: bool = Field(default=False, env="RESEND_TEMPLATE_JOB_FAILURE_ENABLED", description="任务失败邮件模板开关")
    
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
    
    # 前端URL配置（用于Stripe Checkout回调）
    FRONTEND_URL: str = Field(default="http://localhost:3000", env="FRONTEND_URL", description="前端URL（用于Stripe Checkout成功/取消回调）")
    
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
