"""
OAuth 服务基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from shared.models.database.oauth_provider import OAuthProvider
from shared.models.database.user import User
from app.repositories.oauth_repository import OAuthRepository
from sqlalchemy.ext.asyncio import AsyncSession


class OAuthService(ABC):
    """OAuth服务基类"""
    
    def __init__(self):
        self.repository = OAuthRepository()
    
    @abstractmethod
    async def authenticate_user(self, session: AsyncSession, token: str) -> Optional[User]:
        """验证用户身份"""
    
    @abstractmethod
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """获取用户信息"""
    
    async def create_or_update_user(self, session: AsyncSession, user_info: Dict[str, Any], provider: str) -> User:
        """创建或更新用户"""
        # 1. 检查用户是否存在
        user = await self._find_existing_user(session, user_info, provider)
        
        if user:
            # 2. 更新用户信息
            await self._update_user_info(session, user, user_info)
        else:
            # 3. 创建新用户
            user = await self._create_new_user(session, user_info, provider)
        
        return user
    
    async def _find_existing_user(self, session: AsyncSession, user_info: Dict[str, Any], provider: str) -> Optional[User]:
        """查找现有用户"""
        from sqlalchemy import select

        # 根据邮箱查找
        email = user_info.get("email")
        if email:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()
            if user:
                return user
        
        # 根据第三方ID查找
        provider_user_id = user_info.get("id")
        if provider_user_id:
            oauth_record = await self.repository.get_by_provider_user_id(session, provider, provider_user_id)
            if oauth_record:
                result = await session.execute(
                    select(User).where(User.id == oauth_record.user_id)
                )
                return result.scalar_one_or_none()
        
        return None
    
    async def _update_user_info(self, session: AsyncSession, user: User, user_info: Dict[str, Any]):
        """更新用户信息"""
        from datetime import datetime

        from sqlalchemy import update
        
        update_data = {}
        
        # 更新基本信息
        if user_info.get("email") and user.email != user_info["email"]:
            update_data["email"] = user_info["email"]
        if user_info.get("name") and user.username != user_info["name"]:
            update_data["username"] = user_info["name"]
        if user_info.get("picture") and user.avatar_url != user_info["picture"]:
            update_data["avatar_url"] = user_info["picture"]
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(**update_data)
            )
            await session.commit()
    
    async def _create_new_user(self, session: AsyncSession, user_info: Dict[str, Any], provider: str) -> User:
        """创建新用户"""
        import uuid
        from datetime import datetime

        # 创建用户
        user = User(
            id=str(uuid.uuid4()),
            email=user_info["email"],
            username=user_info.get("name"),
            avatar_url=user_info.get("picture"),
            provider_type=provider,
            provider_id=user_info["id"],
            hashed_password="",  # OAuth用户不需要密码
            is_active=True,
            user_type="user",
            credits_balance=100,  # 新用户分配100个免费Credits
            create_time=datetime.utcnow()
        )
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # 创建OAuth提供商记录
        oauth_record = OAuthProvider(
            user_id=user.id,
            provider=provider,
            provider_user_id=user_info["id"],
            provider_email=user_info["email"],
            provider_username=user_info.get("name"),
            access_token=user_info.get("access_token"),
            refresh_token=user_info.get("refresh_token"),
            expires_at=user_info.get("expires_at")
        )
        
        await self.repository.create(session, oauth_record)
        
        return user
    
    async def _get_user_by_email(self, session: AsyncSession, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def _get_user_by_provider_id(self, session: AsyncSession, provider_id: str) -> Optional[User]:
        """根据第三方ID获取用户"""
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.provider_id == provider_id)
        )
        return result.scalar_one_or_none()
