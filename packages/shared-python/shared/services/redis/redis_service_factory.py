"""
Redis服务工厂
"""
import asyncio
import threading
import weakref
from typing import Optional

from shared.core.config.redis import RedisConfigManager
from shared.services.redis.redis_service import RedisService


class RedisServiceFactory:
    """Redis服务工厂"""

    # Per-event-loop cache to avoid sharing asyncio-bound Redis state across loops.
    _services_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[RedisService, RedisConfigManager]]" = weakref.WeakKeyDictionary()
    # Fallback cache for sync contexts without a running loop.
    _thread_local = threading.local()
    _default_config_manager: Optional[RedisConfigManager] = None
    _factory_lock = threading.Lock()

    @classmethod
    def _resolve_config_manager(cls, config_manager: Optional[RedisConfigManager]) -> RedisConfigManager:
        if config_manager is not None:
            return config_manager
        if cls._default_config_manager is None:
            from shared.core.config import settings
            cls._default_config_manager = RedisConfigManager(settings)
        return cls._default_config_manager
    
    @classmethod
    def get_service(cls, config_manager: Optional[RedisConfigManager] = None) -> RedisService:
        """
        获取Redis服务实例
        
        Args:
            config_manager: Redis配置管理器，如果为None则使用默认配置
        
        Returns:
            RedisService实例
        """
        resolved_config = cls._resolve_config_manager(config_manager)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        with cls._factory_lock:
            if loop is not None:
                cached = cls._services_by_loop.get(loop)
                if cached and cached[1] is resolved_config:
                    return cached[0]

                service = RedisService(resolved_config)
                cls._services_by_loop[loop] = (service, resolved_config)
                return service

            cached_sync = getattr(cls._thread_local, "service_tuple", None)
            if cached_sync and cached_sync[1] is resolved_config:
                return cached_sync[0]

            service = RedisService(resolved_config)
            cls._thread_local.service_tuple = (service, resolved_config)
            return service
    
    @classmethod
    def create_service(cls, config_manager: Optional[RedisConfigManager] = None) -> RedisService:
        """
        创建新的Redis服务实例
        
        Args:
            config_manager: Redis配置管理器，如果为None则使用默认配置
        
        Returns:
            新的RedisService实例
        """
        return RedisService(cls._resolve_config_manager(config_manager))

    @classmethod
    async def close_current_service(cls):
        """
        Close and remove Redis service bound to current running loop (if exists).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        with cls._factory_lock:
            cached = cls._services_by_loop.pop(loop, None)

        if cached:
            await cached[0].close()
    
    @classmethod
    def reset(cls):
        """重置工厂状态"""
        cls._services_by_loop = weakref.WeakKeyDictionary()
        cls._thread_local = threading.local()
        cls._default_config_manager = None
