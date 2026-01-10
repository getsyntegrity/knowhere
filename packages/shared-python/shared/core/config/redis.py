"""
Redis配置
"""
import asyncio
import ssl
from typing import Any, Dict, Optional

import redis.asyncio as redis

# ARQ依赖已移除，使用Celery替代
from loguru import logger
from pydantic import BaseModel, Field, field_validator



class RedisConfig(BaseModel):
    """Redis配置"""
    
    # 基础连接配置
    REDIS_HOST: str = Field(default="localhost", description="Redis主机")
    REDIS_PORT: int = Field(default=6379, description="Redis端口")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis密码")
    REDIS_DATABASE: int = Field(default=0, description="Redis数据库")
    
    # SSL/TLS配置 (AWS ElastiCache)
    REDIS_SSL: bool = Field(default=False, description="是否启用SSL连接")
    
    # 连接池配置
    REDIS_MAX_CONNECTIONS: int = Field(default=20, description="最大连接数")
    REDIS_RETRY_ON_TIMEOUT: bool = Field(default=True, description="超时时重试")
    REDIS_SOCKET_TIMEOUT: float = Field(default=5.0, description="Socket超时时间")
    REDIS_SOCKET_CONNECT_TIMEOUT: float = Field(default=5.0, description="连接超时时间")
    
    # 重试配置
    REDIS_MAX_RETRIES: int = Field(default=3, description="最大重试次数")
    REDIS_RETRY_DELAY: float = Field(default=1.0, description="重试延迟时间")
    
    # 键值配置
    REDIS_KEY_PREFIX: str = Field(default="aismart_bid:v1", description="键前缀")
    REDIS_DEFAULT_TTL: int = Field(default=86400, description="默认TTL（秒）")
    
    # 健康检查配置
    REDIS_HEALTH_CHECK_INTERVAL: int = Field(default=30, description="健康检查间隔（秒）")
    REDIS_HEALTH_CHECK_TIMEOUT: float = Field(default=5.0, description="健康检查超时时间")
    
    @field_validator('REDIS_PORT')
    @classmethod
    def validate_port(cls, v):
        """验证端口号"""
        if not 1 <= v <= 65535:
            raise ValueError('端口号必须在1-65535之间')
        return v
    
    @field_validator('REDIS_DATABASE')
    @classmethod
    def validate_database(cls, v):
        """验证数据库编号"""
        if not 0 <= v <= 15:
            raise ValueError('数据库编号必须在0-15之间')
        return v
    
    def get_connection_url(self) -> str:
        """获取Redis连接URL"""
        # AWS ElastiCache使用rediss://协议进行SSL连接
        protocol = "rediss" if self.REDIS_SSL else "redis"
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{protocol}://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DATABASE}"
    
    def get_connection_params(self) -> Dict[str, Any]:
        """获取Redis连接参数"""
        params = {
            'host': self.REDIS_HOST,
            'port': self.REDIS_PORT,
            'db': self.REDIS_DATABASE,
            'max_connections': self.REDIS_MAX_CONNECTIONS,
            'retry_on_timeout': self.REDIS_RETRY_ON_TIMEOUT,
            'socket_timeout': self.REDIS_SOCKET_TIMEOUT,
            'socket_connect_timeout': self.REDIS_SOCKET_CONNECT_TIMEOUT,
            'decode_responses': True
        }
        
        if self.REDIS_PASSWORD:
            params['password'] = self.REDIS_PASSWORD
            
        return params
    
    # ARQ方法已移除，使用Celery替代
    
    def validate_redis_config(self) -> bool:
        """验证Redis配置"""
        try:
            r = redis.Redis(
                host=self.REDIS_HOST,
                port=self.REDIS_PORT,
                password=self.REDIS_PASSWORD,
                db=self.REDIS_DATABASE,
                decode_responses=True
            )
            r.ping()
            logger.info("Redis连接验证成功")
            return True
        except Exception as e:
            logger.error(f"Redis连接验证失败: {e}")
            return False


class RedisPoolManager:
    """Redis连接池管理器 - 已迁移到Celery"""
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self._redis_service = None
        self._lock = asyncio.Lock()

    async def init_pool(self):
        """在应用启动时调用，用于创建和设置连接池"""
        async with self._lock:
            if self._redis_service is None:
                logger.info("正在创建全局 Redis 服务...")
                
                # 初始化Redis服务
                from shared.services.redis import RedisServiceFactory
                config_manager = RedisConfigManager(self.config)
                self._redis_service = RedisServiceFactory.get_service(config_manager)
            else:
                logger.warning("Redis 服务已存在，跳过初始化。")

    async def get_pool(self):
        """获取已初始化的全局 Redis 服务"""
        if self._redis_service is None:
            logger.error("RedisPoolManager.get_pool() 被调用，但服务尚未初始化！")
            raise RuntimeError("redis应该提前初始化！")
        return self._redis_service

    async def close_pool(self):
        """在应用关闭时调用，用于安全关闭连接池"""
        async with self._lock:
            if self._redis_service:
                logger.info("正在关闭全局 Redis 服务...")
                # Redis服务关闭逻辑
                self._redis_service = None

    def get_redis_service(self):
        """获取Redis服务实例"""
        if self._redis_service is None:
            from shared.services.redis import RedisServiceFactory
            config_manager = RedisConfigManager(self.config)
            self._redis_service = RedisServiceFactory.get_service(config_manager)
        return self._redis_service


class RedisConfigManager:
    """Redis配置管理器"""
    
    def __init__(self, config: RedisConfig):
        self.config = config
    
    def get_connection_url(self) -> str:
        """获取连接URL"""
        return self.config.get_connection_url()
    
    def get_connection_params(self) -> Dict[str, Any]:
        """获取连接参数"""
        return self.config.get_connection_params()
    
    # ARQ方法已移除，使用Celery替代
