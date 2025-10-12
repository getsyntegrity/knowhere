"""
数据库模型包
确保所有模型都被正确导入，避免循环导入问题
"""

# 按依赖顺序导入模型
# 1. 先导入基础模型（没有外键依赖的）
from .user import User, Role, UserType

# 2. 再导入依赖User的模型
from .api_key import APIKey
from .subscription import Subscription
from .credits_transaction import CreditsTransaction
from .usage_log import UsageLog

# 3. 最后导入其他模型
# from .oauth_provider import OAuthProvider  # 暂时注释掉，避免循环导入

__all__ = [
    "User",
    "Role", 
    "UserType",
    "APIKey",
    "Subscription",
    "CreditsTransaction",
    "UsageLog",
    # "OAuthProvider"
]
