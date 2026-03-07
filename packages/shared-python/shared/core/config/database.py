"""
数据库配置
"""
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import create_engine


class DatabaseConfig(BaseModel):
    """数据库配置"""
    
    # 数据库配置
    DATABASE_URL: str = Field(..., description="数据库连接URL")
    
    # SSL配置
    DB_SSL_MODE: str = Field(default="prefer", description="数据库SSL模式 (disable, allow, prefer, require, verify-ca, verify-full)")
    DB_SSL_CERT: Optional[str] = Field(default=None, description="SSL证书文件路径")
    DB_SSL_KEY: Optional[str] = Field(default=None, description="SSL私钥文件路径")
    DB_SSL_ROOT_CERT: Optional[str] = Field(default=None, description="SSL根证书文件路径")
    
    # 数据库连接池配置 (async, for API)
    DB_POOL_SIZE: int = Field(default=20, description="连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=30, description="最大溢出连接数")
    DB_POOL_RECYCLE: int = Field(default=1800, description="连接回收时间（秒）")
    DB_POOL_TIMEOUT: int = Field(default=30, description="连接超时时间（秒）")

    # Worker sync database pool config (psycopg2, for gevent worker)
    DB_SYNC_POOL_SIZE: int = Field(default=5, description="Worker sync pool size")
    DB_SYNC_MAX_OVERFLOW: int = Field(default=5, description="Worker sync pool max overflow")

    # Worker concurrency (gevent greenlets)
    WORKER_CONCURRENCY: int = Field(default=50, description="Celery gevent worker concurrency")
    
    def get_ssl_connect_args(self) -> dict:
        """获取SSL连接参数（用于psycopg2）"""
        ssl_args = {"sslmode": self.DB_SSL_MODE}
        
        if self.DB_SSL_CERT:
            ssl_args["sslcert"] = self.DB_SSL_CERT
        if self.DB_SSL_KEY:
            ssl_args["sslkey"] = self.DB_SSL_KEY
        if self.DB_SSL_ROOT_CERT:
            ssl_args["sslrootcert"] = self.DB_SSL_ROOT_CERT
            
        return ssl_args
    
    def get_async_ssl_connect_args(self) -> dict:
        """获取异步SSL连接参数（用于asyncpg）"""
        ssl_args = {}
        
        if self.DB_SSL_MODE and self.DB_SSL_MODE != "disable":
            # asyncpg支持两种SSL配置方式：
            # 1. 简单模式：ssl=True/False
            # 2. 高级模式：ssl=ssl_context对象
            
            if self.DB_SSL_MODE in ["prefer", "require"] and not self.DB_SSL_ROOT_CERT:
                # 简单模式：不需要证书验证
                ssl_args["ssl"] = True
            else:
                # 高级模式：需要证书验证
                import ssl

                # 创建SSL上下文
                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                
                if self.DB_SSL_MODE == "require":
                    # require模式：不验证证书，但强制使用SSL
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                elif self.DB_SSL_MODE == "verify-ca":
                    # verify-ca模式：验证CA证书
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_REQUIRED
                    if self.DB_SSL_ROOT_CERT:
                        ssl_context.load_verify_locations(self.DB_SSL_ROOT_CERT)
                elif self.DB_SSL_MODE == "verify-full":
                    # verify-full模式：验证CA证书和主机名
                    ssl_context.check_hostname = True
                    ssl_context.verify_mode = ssl.CERT_REQUIRED
                    if self.DB_SSL_ROOT_CERT:
                        ssl_context.load_verify_locations(self.DB_SSL_ROOT_CERT)
                else:  # prefer
                    # prefer模式：优先使用SSL，但不强制
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                
                # 客户端证书（如果需要）
                if self.DB_SSL_CERT and self.DB_SSL_KEY:
                    ssl_context.load_cert_chain(self.DB_SSL_CERT, self.DB_SSL_KEY)
                
                ssl_args["ssl"] = ssl_context
            
        return ssl_args
    
    def validate_database_config(self) -> bool:
        """验证数据库配置"""
        try:
            # 使用同步数据库URL进行验证
            sync_url = self.DATABASE_URL.replace("asyncpg", "psycopg2")
            ssl_args = self.get_ssl_connect_args()
            engine = create_engine(sync_url, connect_args=ssl_args)
            engine.connect()
            logger.info("数据库连接验证成功")
            return True
        except Exception as e:
            logger.error(f"数据库连接验证失败: {e}")
            return False
