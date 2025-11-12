"""
OAuth 相关 Schema
"""
from typing import Optional

from pydantic import BaseModel, Field


class AppleLoginRequest(BaseModel):
    """Apple登录请求"""
    id_token: str = Field(..., description="Apple ID Token")
    authorization_code: Optional[str] = Field(default=None, description="授权码")


class GoogleLoginRequest(BaseModel):
    """Google登录请求"""
    id_token: str = Field(..., description="Google ID Token")


class GitHubLoginRequest(BaseModel):
    """GitHub登录请求"""
    code: str = Field(..., description="GitHub授权码")
    state: Optional[str] = Field(default=None, description="状态参数")


class OAuthLoginResponse(BaseModel):
    """OAuth登录响应"""
    access_token: str
    token_type: str = "bearer"
    user_info: dict


class OAuthProviderResponse(BaseModel):
    """OAuth提供商信息响应"""
    id: str
    provider: str
    provider_email: Optional[str]
    provider_username: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True
