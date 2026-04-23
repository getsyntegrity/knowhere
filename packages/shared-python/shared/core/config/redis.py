"""Redis configuration."""
import asyncio
import ssl
from typing import Any, Dict, Optional

import redis.asyncio as redis

# ARQ support was removed in favor of Celery.
from loguru import logger
from pydantic import BaseModel, Field, field_validator



class RedisConfig(BaseModel):
    """Redis configuration."""

    # Basic connection settings.
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")
    REDIS_DATABASE: int = Field(default=0, description="Redis database")

    # SSL/TLS configuration (for example, AWS ElastiCache).
    REDIS_SSL: bool = Field(default=False, description="Enable SSL/TLS connections")

    # Connection-pool configuration.
    REDIS_MAX_CONNECTIONS: int = Field(default=20, description="Maximum connections")
    REDIS_RETRY_ON_TIMEOUT: bool = Field(default=True, description="Retry on timeout")
    REDIS_SOCKET_TIMEOUT: float = Field(default=5.0, description="Socket timeout in seconds")
    REDIS_SOCKET_CONNECT_TIMEOUT: float = Field(default=5.0, description="Socket connect timeout in seconds")

    # Retry configuration.
    REDIS_MAX_RETRIES: int = Field(default=3, description="Maximum retry count")
    REDIS_RETRY_DELAY: float = Field(default=1.0, description="Retry delay in seconds")

    # Key configuration.
    REDIS_KEY_PREFIX: str = Field(default="knowhere-api", description="Key prefix")
    REDIS_DEFAULT_TTL: int = Field(default=86400, description="Default TTL in seconds")
    
    # Worker sync pool config (gevent BlockingConnectionPool)
    REDIS_SYNC_MAX_CONNECTIONS: int = Field(default=50, description="Worker sync pool max connections")
    REDIS_SYNC_POOL_TIMEOUT: int = Field(default=5, description="Worker sync pool blocking timeout (seconds)")

    # Health-check configuration.
    REDIS_HEALTH_CHECK_INTERVAL: int = Field(default=30, description="Health-check interval in seconds")
    REDIS_HEALTH_CHECK_TIMEOUT: float = Field(default=5.0, description="Health-check timeout in seconds")
    
    @field_validator('REDIS_PORT')
    @classmethod
    def validate_port(cls, v):
        """Validate the port number."""
        if not 1 <= v <= 65535:
            raise ValueError('REDIS_PORT must be between 1 and 65535')
        return v
    
    @field_validator('REDIS_DATABASE')
    @classmethod
    def validate_database(cls, v):
        """Validate the Redis database index."""
        if not 0 <= v <= 15:
            raise ValueError('REDIS_DATABASE must be between 0 and 15')
        return v
    
    def get_connection_url(self) -> str:
        """Return the Redis connection URL."""
        # AWS ElastiCache uses the rediss:// scheme when SSL is enabled.
        protocol = "rediss" if self.REDIS_SSL else "redis"
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{protocol}://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DATABASE}"
    
    def get_connection_params(self) -> Dict[str, Any]:
        """Return Redis connection parameters."""
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
    
    # ARQ-specific helpers were removed in favor of Celery.
    
    def validate_redis_config(self) -> bool:
        """Validate the Redis configuration by pinging the server."""
        try:
            r = redis.Redis(
                host=self.REDIS_HOST,
                port=self.REDIS_PORT,
                password=self.REDIS_PASSWORD,
                db=self.REDIS_DATABASE,
                decode_responses=True
            )
            r.ping()
            logger.info("Redis connection validation succeeded")
            return True
        except Exception as e:
            logger.error(f"Redis connection validation failed: {e}")
            return False


class RedisPoolManager:
    """Manage the shared Redis service used by Celery-backed code."""
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self._redis_service = None
        self._lock = asyncio.Lock()

    async def init_pool(self):
        """Initialize the shared Redis service during application startup."""
        async with self._lock:
            if self._redis_service is None:
                logger.info("Creating the shared Redis service...")

                # Initialize the Redis service.
                from shared.services.redis import RedisServiceFactory
                config_manager = RedisConfigManager(self.config)
                self._redis_service = RedisServiceFactory.get_service(config_manager)
            else:
                logger.warning("The shared Redis service already exists; skipping initialization.")

    async def get_pool(self):
        """Return the initialized shared Redis service."""
        if self._redis_service is None:
            logger.error("RedisPoolManager.get_pool() was called before the service was initialized")
            raise RuntimeError("Redis must be initialized before use")
        return self._redis_service

    async def close_pool(self):
        """Clear the shared Redis service during application shutdown."""
        async with self._lock:
            if self._redis_service:
                logger.info("Closing the shared Redis service...")
                # Redis service shutdown logic.
                self._redis_service = None

    def get_redis_service(self):
        """Return the shared Redis service instance."""
        if self._redis_service is None:
            from shared.services.redis import RedisServiceFactory
            config_manager = RedisConfigManager(self.config)
            self._redis_service = RedisServiceFactory.get_service(config_manager)
        return self._redis_service


class RedisConfigManager:
    """Expose Redis configuration in the shape expected by shared services."""
    
    def __init__(self, config: RedisConfig):
        self.config = config
    
    def get_connection_url(self) -> str:
        """Return the Redis connection URL."""
        return self.config.get_connection_url()
    
    def get_connection_params(self) -> Dict[str, Any]:
        """Return Redis connection parameters."""
        return self.config.get_connection_params()

    # ARQ-specific helpers were removed in favor of Celery.
