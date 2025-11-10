"""
Redis相关异常定义
"""

class RedisConnectionError(Exception):
    """Redis连接异常"""
    pass

class RedisOperationError(Exception):
    """Redis操作异常"""
    pass

class RedisTimeoutError(Exception):
    """Redis超时异常"""
    pass

class RedisConfigurationError(Exception):
    """Redis配置异常"""
    pass
