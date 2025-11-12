"""
应用配置
整合所有配置组件
"""
from .ai import AIConfig
from .auth import AuthConfig
from .base import BaseConfig
from .billing import BillingConfig
from .celery import CeleryConfig
from .database import DatabaseConfig
from .redis import RedisConfig, RedisConfigManager, RedisPoolManager
from .storage import StorageConfig


class AppConfig(BaseConfig, DatabaseConfig, RedisConfig, CeleryConfig, StorageConfig, AIConfig, AuthConfig, BillingConfig):
    """应用配置 - 整合所有配置组件"""
    
    def validate_all(self) -> bool:
        """验证所有配置"""
        validations = [
            self.validate_file_paths(),
            self.validate_database_config(),
            self.validate_redis_config(),
            self.validate_auth_config(),
            self.validate_billing_config()
        ]
        
        return all(validations)


# 创建全局配置实例
app_config = AppConfig()

# 向后兼容的别名
settings = app_config

# 创建Redis连接池管理器
redis_pool_manager = RedisPoolManager(app_config)

# 创建Redis配置管理器
redis_config_manager = RedisConfigManager(app_config)
