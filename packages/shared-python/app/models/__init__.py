"""
模型注册表 - 解决循环导入问题
"""
from app.core.database import Base

# 导入所有模型以确保它们被注册
from app.models.database.user import User
from app.models.database.api_key import APIKey
from app.models.database.job import Job
from app.models.database.subscription import Subscription
from app.models.database.credits_transaction import CreditsTransaction
from app.models.database.usage_log import UsageLog
from app.models.database.job_state_history import JobStateHistory
from app.models.database.webhook_log import WebhookLog
from app.models.database.oauth_provider import OAuthProvider

# 确保所有模型都被正确注册
__all__ = [
    "User",
    "APIKey", 
    "Job",
    "Subscription",
    "CreditsTransaction",
    "UsageLog",
    "JobStateHistory",
    "WebhookLog",
    "OAuthProvider"
]
