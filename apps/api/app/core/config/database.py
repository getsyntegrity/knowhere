"""
数据库配置
"""
from pydantic import Field
from typing import Optional
import redis
from sqlalchemy import create_engine
from loguru import logger
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """数据库配置"""
    
    # 数据库配置
    DATABASE_URL: str = Field(..., description="数据库连接URL")
    
    # 数据库连接池配置
    DB_POOL_SIZE: int = Field(default=20, description="连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=30, description="最大溢出连接数")
    DB_POOL_RECYCLE: int = Field(default=1800, description="连接回收时间（秒）")
    DB_POOL_TIMEOUT: int = Field(default=30, description="连接超时时间（秒）")
    
    def validate_database_config(self) -> bool:
        """验证数据库配置"""
        try:
            # 使用同步数据库URL进行验证
            sync_url = self.DATABASE_URL.replace("asyncpg", "psycopg2")
            engine = create_engine(sync_url)
            engine.connect()
            logger.info("数据库连接验证成功")
            return True
        except Exception as e:
            logger.error(f"数据库连接验证失败: {e}")
            return False
