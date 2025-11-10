"""
认证相关配置
"""
from pydantic import Field
from typing import Optional
from pydantic_settings import BaseSettings


class AuthConfig(BaseSettings):
    """认证配置"""
    
    # JWT 配置 (SECRET_KEY已在BaseConfig中定义)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, description="访问令牌过期时间（分钟）")
    
    # 用户验证配置
    USERS_VERIFY_TOKEN_SECRET: str = Field(default="", description="用户验证令牌密钥")
    USERS_RESET_PASSWORD_TOKEN_SECRET: str = Field(default="", description="密码重置令牌密钥")
    
    # 邮件配置（可选）
    SMTP_TLS: bool = Field(default=True, description="SMTP TLS")
    SMTP_PORT: Optional[int] = Field(default=None, description="SMTP 端口")
    SMTP_HOST: Optional[str] = Field(default=None, description="SMTP 主机")
    SMTP_USER: Optional[str] = Field(default=None, description="SMTP 用户名")
    SMTP_PASSWORD: Optional[str] = Field(default=None, description="SMTP 密码")
    EMAILS_FROM_EMAIL: Optional[str] = Field(default=None, description="发件人邮箱")
    EMAILS_FROM_NAME: Optional[str] = Field(default=None, description="发件人名称")
    
    # OAuth 配置
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, description="Google OAuth 客户端ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, description="Google OAuth 客户端密钥")
    GITHUB_CLIENT_ID: Optional[str] = Field(default=None, description="GitHub OAuth 客户端ID")
    GITHUB_CLIENT_SECRET: Optional[str] = Field(default=None, description="GitHub OAuth 客户端密钥")
    APPLE_CLIENT_ID: Optional[str] = Field(default=None, description="Apple OAuth 客户端ID")
    APPLE_CLIENT_SECRET: Optional[str] = Field(default=None, description="Apple OAuth 客户端密钥")
    
    def validate_auth_config(self) -> bool:
        """验证认证配置"""
        required_fields = [
            self.USERS_VERIFY_TOKEN_SECRET,
            self.USERS_RESET_PASSWORD_TOKEN_SECRET
        ]
        return all(field for field in required_fields)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
