"""
基础配置类
"""
import os

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class BaseConfig(BaseSettings):
    """基础配置类"""
    
    # 环境配置
    ENVIRONMENT: str = Field(default="development", description="运行环境")
    DEBUG: bool = Field(default=False, description="调试模式")
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    
    # 应用基础配置
    APP_TITLE: str = Field(default="Konwhere AI知识库管理系统", description="应用标题")
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    APP_DESCRIPTION: str = Field(default="基于AI的知识库管理和智能问答系统", description="应用描述")
    
    # 安全配置
    SECRET_KEY: str = Field(..., description="JWT密钥")
    ALGORITHM: str = Field(default="HS256", description="JWT算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, description="访问令牌过期时间（分钟）")
    
    # 路径配置
    TMP_PATH: str = Field(..., description="临时文件路径")
    FONT_PATH: str = Field(..., description="字体文件路径")
    CHROMEDRIVER_PATH: str = Field(..., description="Chrome驱动路径")
    
    @field_validator('ENVIRONMENT')
    @classmethod
    def validate_environment(cls, v):
        """验证环境配置"""
        if v not in ['development', 'staging', 'production']:
            raise ValueError('ENVIRONMENT must be development, staging, or production')
        return v
    
    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v):
        """验证日志级别"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'LOG_LEVEL must be one of {valid_levels}')
        return v.upper()
    
    def validate_file_paths(self) -> bool:
        """验证文件路径"""
        paths_to_check = {
            'TMP_PATH': self.TMP_PATH,
            'FONT_PATH': self.FONT_PATH,
            'CHROMEDRIVER_PATH': self.CHROMEDRIVER_PATH
        }
        
        for name, path in paths_to_check.items():
            if not os.path.exists(path):
                logger.warning(f"路径不存在: {name} = {path}")
                return False
        
        logger.info("文件路径验证成功")
        return True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的环境变量
