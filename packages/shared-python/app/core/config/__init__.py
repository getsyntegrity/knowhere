"""
统一配置管理
"""
from .base import BaseConfig
from .database import DatabaseConfig
from .redis import RedisConfig, RedisConfigManager, RedisPoolManager
from .celery import CeleryConfig
from .storage import StorageConfig
from .ai import AIConfig
from .app import AppConfig
from .messaging import MessagingConfig, messaging_config

# 统一配置实例
from .app import app_config, settings, redis_pool_manager, redis_config_manager

__all__ = [
    'BaseConfig',
    'DatabaseConfig', 
    'RedisConfig',
    'RedisConfigManager',
    'RedisPoolManager',
    'CeleryConfig',
    'StorageConfig',
    'AIConfig',
    'AppConfig',
    'MessagingConfig',
    'app_config',
    'settings',  # 向后兼容
    'redis_pool_manager',
    'redis_config_manager',
    'messaging_config',
]
