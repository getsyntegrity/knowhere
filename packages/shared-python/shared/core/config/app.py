"""
Application configuration — assembles all config components.
"""
from .ai import AIConfig
from .base import BaseConfig
from .billing import BillingConfig
from .celery import CeleryConfig
from .database import DatabaseConfig
from .job import JobConfig
from .mineru import MineruConfig
from .qstash import QStashConfig
from .redis import RedisConfig, RedisConfigManager, RedisPoolManager
from .storage import StorageConfig
from pydantic_settings import SettingsConfigDict


class AppConfig(BaseConfig, DatabaseConfig, RedisConfig, CeleryConfig, QStashConfig, StorageConfig, AIConfig, MineruConfig, BillingConfig, JobConfig):
    """Application configuration — all config components merged."""
    
    def validate_all(self) -> bool:
        """验证所有配置"""
        validations = [
            self.validate_file_paths(),
            self.validate_database_config(),
            self.validate_redis_config(),
            self.validate_billing_config()
        ]
        
        return all(validations)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# 创建全局配置实例
app_config = AppConfig()

# 向后兼容的别名
settings = app_config

# 创建Redis连接池管理器
redis_pool_manager = RedisPoolManager(app_config)

# 创建Redis配置管理器
redis_config_manager = RedisConfigManager(app_config)
