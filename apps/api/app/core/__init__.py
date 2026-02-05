"""
核心模块统一导入接口
重构后的配置管理、Redis管理等功能
注意：共享包内容需要从共享包导入
"""

# 从共享包导入
from shared.core.config import app_config, redis_config_manager, redis_pool_manager
from shared.core.constants import (APIConstants, BusinessConstants,
                                   ProcessingConstants, SystemConstants)
from shared.core.database import get_db
from shared.core.logging import setup_logging
from shared.core.security import get_password_hash, verify_password

from .dependencies import (get_current_user_id)

# 响应处理 - API专用，保留在API中
from .response import ResponseCode

# 向后兼容的别名
settings = app_config

__all__ = [
    # 配置
    'app_config',
    'settings',  # 向后兼容
    
    # Redis
    'redis_config_manager',
    'redis_pool_manager',
    
    # 数据库
    'get_db',
    
    # 安全
    'get_password_hash',
    'verify_password',

    # 依赖
    'get_current_user_id',
    
    # 响应
    'ResponseCode',
    
    # 常量
    'SystemConstants',
    'BusinessConstants',
    'APIConstants',
    'ProcessingConstants',
    
    # 日志
    'setup_logging'
]
