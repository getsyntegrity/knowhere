"""
Redis服务工厂
"""
from typing import Optional

from shared.core.config.redis import RedisConfigManager
from shared.services.redis.redis_service import RedisService


class RedisServiceFactory:
    """Redis服务工厂"""
    
    _instance: Optional[RedisService] = None
    _config_manager: Optional[RedisConfigManager] = None
    
    @classmethod
    def get_service(cls, config_manager: Optional[RedisConfigManager] = None) -> RedisService:
        """
        获取Redis服务实例
        
        Args:
            config_manager: Redis配置管理器，如果为None则使用默认配置
        
        Returns:
            RedisService实例
        """
        if cls._instance is None or config_manager != cls._config_manager:
            if config_manager is None:
                from shared.core.config import settings
                cls._config_manager = RedisConfigManager(settings)
            else:
                cls._config_manager = config_manager
            cls._instance = RedisService(cls._config_manager)
        
        return cls._instance
    
    @classmethod
    def create_service(cls, config_manager: Optional[RedisConfigManager] = None) -> RedisService:
        """
        创建新的Redis服务实例
        
        Args:
            config_manager: Redis配置管理器，如果为None则使用默认配置
        
        Returns:
            新的RedisService实例
        """
        if config_manager is None:
            from shared.core.config import settings
            config_manager = RedisConfigManager(settings)
        return RedisService(config_manager)
    
    @classmethod
    def reset(cls):
        """重置工厂状态"""
        if cls._instance:
            # 这里可以添加清理逻辑
            pass
        cls._instance = None
        cls._config_manager = None
