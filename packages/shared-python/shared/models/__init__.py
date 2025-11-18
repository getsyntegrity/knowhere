"""
模型注册表 - 解决循环导入问题
"""
from shared.models.database.api_key import APIKey
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.job import Job
from shared.models.database.job_state_history import JobStateHistory
from shared.models.database.oauth_provider import OAuthProvider
from shared.models.database.subscription import Subscription
from shared.models.database.usage_log import UsageLog

# 导入所有模型以确保它们被注册
from shared.models.database.user import User
from shared.models.database.webhook_log import WebhookLog

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
