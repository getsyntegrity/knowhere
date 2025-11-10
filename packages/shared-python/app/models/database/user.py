from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fastapi_users.db import SQLAlchemyBaseUserTableUUID

from app.core.database import Base

"""
所有与用户信息相关的表
这是基础类
"""
def utc_now():
    return datetime.utcnow()

class UserType(str, Enum):
    """用户类型枚举"""
    USER = "user"           # 普通用户
    ADMIN = "admin"         # 管理员
    SUPERUSER = "superuser" # 超级用户

class User(SQLAlchemyBaseUserTableUUID, Base):
    """用户模型 - 继承 FastAPI Users 基础用户表"""
    __tablename__ = "users"
    
    # FastAPI Users 默认字段（自动包含）:
    # - id: UUID (主键)
    # - email: str (唯一，必填)
    # - hashed_password: str (必填)
    # - is_active: bool (默认 True)
    # - is_superuser: bool (默认 False)
    # - is_verified: bool (默认 False)
    
    # 自定义字段
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, 
        nullable=True, 
        default=utc_now
    )
    
    # 开放API管理相关字段
    provider_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 认证提供商类型
    provider_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)   # 第三方用户ID
    credits_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Credits余额
    subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 订阅ID
    user_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        default=UserType.USER.value
    )
    
    def is_admin(self) -> bool:
        """检查是否为管理员"""
        return self.user_type in [UserType.ADMIN.value, UserType.SUPERUSER.value]
    
    def is_superuser(self) -> bool:
        """检查是否为超级用户"""
        return self.user_type == UserType.SUPERUSER.value
    
    # 开放API管理相关关系 - 使用SQLAlchemy 2.0最佳实践，考虑lazy加载
    api_keys: Mapped[List[APIKey]] = relationship(
        "APIKey", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="select"  # 默认lazy加载
    )
    subscriptions: Mapped[List[Subscription]] = relationship(
        "Subscription", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    credits_transactions: Mapped[List[CreditsTransaction]] = relationship(
        "CreditsTransaction", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    jobs: Mapped[List[Job]] = relationship(
        "Job", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    usage_logs: Mapped[List[UsageLog]] = relationship(
        "UsageLog", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="select"
    )

    def has_role(self, role_name: str) -> bool:
        """检查用户是否具有指定角色"""
        # 基于用户类型进行角色检查
        if role_name == "admin":
            return self.user_type in [UserType.ADMIN.value, UserType.SUPERUSER.value]
        elif role_name == "superuser":
            return self.user_type == UserType.SUPERUSER.value
        elif role_name == "user":
            return True  # 所有用户都有基础用户角色
        return False

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

class Role(Base):
    __tablename__ = "roles"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()))
    name: str = Column(String(50), unique=True, nullable=False)
    description: str = Column(String(255), nullable=True)
    # users: Mapped[List["User"]] = relationship(
    #     "User",
    #     secondary=user_roles_association,
    #     back_populates="roles"
    # )  # 暂时注释掉避免循环导入
