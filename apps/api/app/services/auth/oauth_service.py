"""
OAuth 服务基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from shared.core.billing import MicroDollar

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
        """创建或更新用户 - 支持多OAuth提供商"""
        # 1. 检查用户是否存在（通过邮箱或OAuth提供商）
        user = await self._find_existing_user(session, user_info, provider)
        
        if user:
            # 2. 用户已存在，更新用户信息和OAuth提供商记录
            await self._update_user_info(session, user, user_info)
            await self._ensure_oauth_provider(session, user, user_info, provider)
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
        
        # 更新基本信息（不覆盖已有值，除非新值更完整）
        if user_info.get("email") and user.email != user_info["email"]:
            update_data["email"] = user_info["email"]
        if user_info.get("name") and (not user.username or user.username != user_info["name"]):
            update_data["username"] = user_info["name"]
        if user_info.get("picture") and (not user.avatar_url or user.avatar_url != user_info["picture"]):
            update_data["avatar_url"] = user_info["picture"]
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(**update_data)
            )
            await session.commit()
    
    async def _ensure_oauth_provider(self, session: AsyncSession, user: User, user_info: Dict[str, Any], provider: str):
        """确保OAuth提供商记录存在（支持多OAuth提供商）
        
        确保每个用户每个OAuth类型只有一条记录：
        - 如果用户已有该provider的记录，更新该记录的所有信息
        - 如果用户没有该provider的记录，创建新记录
        """
        from datetime import datetime
        
        provider_user_id = user_info.get("id")
        if not provider_user_id:
            return
        
        # 首先检查用户是否已有该provider的记录（通过user_id和provider，确保每个用户每个provider只有一条）
        existing_oauth = await self.repository.get_by_provider_and_user_id(session, provider, str(user.id))
        
        if existing_oauth:
            # 用户已有该provider的记录，更新完整信息（包括用户信息和token）
            # 如果provider_user_id发生变化，也需要更新
            update_needed = False
            if existing_oauth.provider_user_id != provider_user_id:
                # provider_user_id变化，需要更新（虽然这种情况很少见）
                from sqlalchemy import update
                await session.execute(
                    update(OAuthProvider)
                    .where(OAuthProvider.id == existing_oauth.id)
                    .values(provider_user_id=provider_user_id)
                )
                update_needed = True
            
            # 更新OAuth提供商的所有信息（用户信息 + token信息）
            await self.repository.update_oauth_provider(
                session,
                existing_oauth.id,
                user_info,
                user_info.get("access_token"),
                user_info.get("refresh_token"),
                user_info.get("expires_at")
            )
            
            if update_needed:
                await session.commit()
        else:
            # 用户没有该provider的记录，创建新记录
            # 但需要检查是否已有相同provider_user_id的记录（防止重复）
            existing_by_provider_id = await self.repository.get_by_provider_user_id(session, provider, provider_user_id)
            
            if existing_by_provider_id and existing_by_provider_id.user_id != user.id:
                # 这种情况不应该发生，但如果发生了，说明provider_user_id被其他用户使用
                # 这种情况下，我们仍然为当前用户创建新记录（因为唯一约束是(provider, provider_user_id)）
                # 但实际上这种情况应该很少见，因为provider_user_id通常是唯一的
                pass
            
            # 创建新的OAuth提供商记录
            oauth_record = OAuthProvider(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_email=user_info.get("email"),
                provider_username=user_info.get("name"),
                access_token=user_info.get("access_token"),
                refresh_token=user_info.get("refresh_token"),
                expires_at=user_info.get("expires_at")
            )
            await self.repository.create(session, oauth_record)
        
        # 更新User表的provider_type和provider_id（用于兼容性，保留最后一次登录的提供商）
        from sqlalchemy import update
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                provider_type=provider,
                provider_id=provider_user_id,
                updated_at=datetime.utcnow()
            )
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
            credits_balance=MicroDollar.from_dollars(100),  # assign 100 micro dollars for new user
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
