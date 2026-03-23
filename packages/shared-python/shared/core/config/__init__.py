"""
统一配置管理
"""
from .ai import AIConfig

# 统一配置实例
from .app import (
    AppConfig,
    app_config,
    redis_config_manager,
    redis_pool_manager,
    settings,
)
from .base import BaseConfig
from .celery import CeleryConfig
from .database import DatabaseConfig
from .job import JobConfig
from .messaging import MessagingConfig, messaging_config
from .mineru import MineruConfig
from .redis import RedisConfig, RedisConfigManager, RedisPoolManager
from .storage import StorageConfig

__all__ = [
    'BaseConfig',
    'DatabaseConfig',
    'RedisConfig',
    'RedisConfigManager',
    'RedisPoolManager',
    'CeleryConfig',
    'StorageConfig',
    'JobConfig',
    'AIConfig',
    'MineruConfig',
    'AppConfig',
    'MessagingConfig',
    'app_config',
    'settings',  # 向后兼容
    'redis_pool_manager',
    'redis_config_manager',
    'messaging_config',
]
