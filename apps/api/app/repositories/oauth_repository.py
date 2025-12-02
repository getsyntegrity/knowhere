"""
OAuth 数据访问层
"""
from datetime import datetime
from typing import List, Optional

from shared.models.database.oauth_provider import OAuthProvider
from app.repositories.base_repository import BaseRepository
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


class OAuthRepository(BaseRepository[OAuthProvider, dict, dict]):
    """OAuth 数据访问"""
    
    def __init__(self):
        super().__init__(OAuthProvider)
    
    async def get_by_user_id(self, session: AsyncSession, user_id: str) -> List[OAuthProvider]:
        """获取用户的所有OAuth提供商"""
        result = await session.execute(
            select(OAuthProvider)
            .where(OAuthProvider.user_id == user_id)
            .order_by(OAuthProvider.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_by_provider_and_user_id(self, session: AsyncSession, provider: str, user_id: str) -> Optional[OAuthProvider]:
        """根据提供商和用户ID获取OAuth记录"""
        result = await session.execute(
            select(OAuthProvider)
            .where(and_(
                OAuthProvider.provider == provider,
                OAuthProvider.user_id == user_id
            ))
        )
        return result.scalar_one_or_none()
    
    async def get_by_provider_user_id(self, session: AsyncSession, provider: str, provider_user_id: str) -> Optional[OAuthProvider]:
        """根据提供商和提供商用户ID获取OAuth记录"""
        result = await session.execute(
            select(OAuthProvider)
            .where(and_(
                OAuthProvider.provider == provider,
                OAuthProvider.provider_user_id == provider_user_id
            ))
        )
        return result.scalar_one_or_none()
    
    async def get_by_provider_email(self, session: AsyncSession, provider: str, email: str) -> Optional[OAuthProvider]:
        """根据提供商和邮箱获取OAuth记录"""
        result = await session.execute(
            select(OAuthProvider)
            .where(and_(
                OAuthProvider.provider == provider,
                OAuthProvider.provider_email == email
            ))
        )
        return result.scalar_one_or_none()
    
    async def update_tokens(self, session: AsyncSession, oauth_id: str, access_token: Optional[str] = None, refresh_token: Optional[str] = None, expires_at: Optional[datetime] = None) -> bool:
        """更新访问令牌"""
        from datetime import datetime
        from sqlalchemy import update
        
        update_data = {
            "updated_at": datetime.utcnow()
        }
        
        if access_token is not None:
            update_data["access_token"] = access_token
        if refresh_token is not None:
            update_data["refresh_token"] = refresh_token
        if expires_at is not None:
            update_data["expires_at"] = expires_at
        
        result = await session.execute(
            update(OAuthProvider)
            .where(OAuthProvider.id == oauth_id)
            .values(**update_data)
        )
        await session.commit()
        return result.rowcount > 0
    
    async def update_oauth_provider(self, session: AsyncSession, oauth_id: str, user_info: dict, access_token: Optional[str] = None, refresh_token: Optional[str] = None, expires_at: Optional[datetime] = None) -> bool:
        """更新OAuth提供商完整信息（包括用户信息和token）"""
        from datetime import datetime
        from sqlalchemy import update
        
        update_data = {
            "updated_at": datetime.utcnow()
        }
        
        # 更新用户信息
        if user_info.get("email"):
            update_data["provider_email"] = user_info["email"]
        if user_info.get("name"):
            update_data["provider_username"] = user_info["name"]
        
        # 更新token信息
        if access_token is not None:
            update_data["access_token"] = access_token
        if refresh_token is not None:
            update_data["refresh_token"] = refresh_token
        if expires_at is not None:
            update_data["expires_at"] = expires_at
        
        result = await session.execute(
            update(OAuthProvider)
            .where(OAuthProvider.id == oauth_id)
            .values(**update_data)
        )
        await session.commit()
        return result.rowcount > 0
    
    async def get_expired_tokens(self, session: AsyncSession) -> List[OAuthProvider]:
        """获取过期的令牌"""
        from datetime import datetime
        result = await session.execute(
            select(OAuthProvider)
            .where(OAuthProvider.expires_at < datetime.utcnow())
            .where(OAuthProvider.refresh_token.isnot(None))
        )
        return result.scalars().all()
