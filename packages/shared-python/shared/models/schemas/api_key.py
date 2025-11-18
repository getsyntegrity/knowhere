"""
API Key 相关 Schema
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateAPIKeyRequest(BaseModel):
    """创建API Key请求"""
    name: str = Field(..., min_length=1, max_length=255, description="API Key名称")
    enabled_modules: Optional[List[str]] = Field(default=None, description="启用的功能模块")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")


class APIKeyResponse(BaseModel):
    """API Key响应"""
    id: str
    name: str
    api_key: str  # 掩码后的API密钥
    enabled_modules: Optional[List[str]]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class CreateAPIKeyResponse(BaseModel):
    """创建API Key响应"""
    api_key: str = Field(..., description="生成的API Key（仅创建时返回）")
    name: str
    enabled_modules: Optional[List[str]]
    expires_at: Optional[datetime]


class RegenerateAPIKeyRequest(BaseModel):
    """重新生成API Key请求"""
    api_key_id: str = Field(..., description="要重新生成的API Key ID")


class RevokeAPIKeyRequest(BaseModel):
    """撤销API Key请求"""
    api_key_id: str = Field(..., description="要撤销的API Key ID")


class APIKeyListResponse(BaseModel):
    """API Key列表响应"""
    api_keys: List[APIKeyResponse]
    total: int
