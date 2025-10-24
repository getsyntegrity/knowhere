"""
核心模块统一导入接口
重构后的配置管理、Redis管理等功能
"""

# 配置管理 - 使用新的配置结构
from .config import app_config, redis_config_manager, redis_pool_manager

# 数据库管理
from .database import get_db

# 安全认证
from .security import (
    get_password_hash,
    verify_password
)

# 依赖注入
from .dependencies import (
    get_current_user,
    get_redis_service,
    get_redis_service_factory
)

# 响应处理
from .response import (
    ResponseCode
)

# 常量定义
from .constants import (
    SystemConstants,
    BusinessConstants,
    APIConstants,
    ProcessingConstants
)

# 日志配置
from .logging import setup_logging

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
    'get_current_user',
    'get_redis_service',
    'get_redis_service_factory',
    
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
