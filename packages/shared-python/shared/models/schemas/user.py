"""
用户相关 Schema
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi_users.schemas import BaseUserUpdate
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# from shared.models.database.user import UserType


class UserBase(BaseModel):
    """用户基础信息"""
    email: EmailStr = Field(..., description="邮箱地址")
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
    phone: Optional[str] = Field(None, pattern=r"^1[3-9]\d{9}$", description="手机号")
    user_type: str = Field(default="user", description="用户类型")


class UserCreate(UserBase):
    """创建用户请求"""
    password: str = Field(..., min_length=6, description="密码")
    
    def create_update_dict(self) -> dict:
        """创建更新字典，FastAPI Users 需要此方法"""
        return self.model_dump(exclude_unset=True)


class UserUpdate(BaseUserUpdate):
    """用户更新模型"""
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
    phone: Optional[str] = Field(None, pattern=r"^1[3-9]\d{9}$", description="手机号")
    avatar_url: Optional[str] = Field(None, description="头像URL")


class UserRead(UserBase):
    """用户读取模型"""
    id: UUID = Field(..., description="用户ID")
    is_active: bool = Field(..., description="是否激活")
    is_verified: bool = Field(..., description="是否已验证")
    is_superuser: bool = Field(..., description="是否超级用户")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    create_time: Optional[datetime] = Field(None, description="创建时间")
    
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        """自定义验证，处理方法字段"""
        if hasattr(obj, 'is_superuser') and callable(obj.is_superuser):
            # 如果是方法，调用它获取布尔值
            obj.is_superuser = obj.is_superuser()
        return super().model_validate(obj, *args, **kwargs)
    
    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    """更新用户请求"""
    username: Optional[str] = Field(None, description="用户名")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    phone: Optional[str] = Field(None, description="手机号")


class UserResponse(UserBase):
    """用户响应"""
    id: str = Field(..., description="用户ID")
    credits_balance: int = Field(0, description="Credits余额")
    stripe_customer_id: Optional[str] = Field(None, description="Stripe客户ID")
    provider_type: Optional[str] = Field(None, description="认证提供商类型")
    create_time: Optional[datetime] = Field(None, description="创建时间")
    is_active: bool = Field(True, description="是否激活")
    is_verified: bool = Field(False, description="是否已验证")
    
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        """自定义验证，将UUID转换为字符串"""
        # 创建一个副本，避免修改原始对象
        if hasattr(obj, '__dict__'):
            data = obj.__dict__.copy()
        else:
            data = dict(obj)
        
        # 将UUID转换为字符串
        if 'id' in data and data['id'] is not None:
            data['id'] = str(data['id'])
        
        return super().model_validate(data, *args, **kwargs)
    
    model_config = ConfigDict(from_attributes=True)


class UserStatsResponse(BaseModel):
    """用户统计信息响应"""
    user_id: str = Field(..., description="用户ID")
    credits_balance: int = Field(0, description="Credits余额")
    api_keys_count: int = Field(0, description="API Key数量")
    subscriptions_count: int = Field(0, description="订阅数量")
    usage_logs_count: int = Field(0, description="使用日志数量")
    user_type: str = Field("user", description="用户类型")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class UserListResponse(BaseModel):
    """用户列表响应"""
    users: List[UserResponse] = Field(..., description="用户列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页数量")


class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    user: UserResponse = Field(..., description="用户信息")


class RegisterRequest(UserCreate):
    """注册请求"""


class RegisterResponse(BaseModel):
    """注册响应"""
    message: str = Field(..., description="响应消息")
    user: UserResponse = Field(..., description="用户信息")