"""
Redis相关异常定义
"""

class RedisConnectionError(Exception):
    """Redis连接异常"""

class RedisOperationError(Exception):
    """Redis操作异常"""

class RedisTimeoutError(Exception):
    """Redis超时异常"""

class RedisConfigurationError(Exception):
    """Redis配置异常"""
