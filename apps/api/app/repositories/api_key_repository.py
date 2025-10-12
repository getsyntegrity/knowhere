"""
API Key 数据访问层
"""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.models.database.api_key import APIKey
from app.repositories.base_repository import BaseRepository


class APIKeyRepository(BaseRepository[APIKey, dict, dict]):
    """API Key 数据访问"""
    
    def __init__(self):
        super().__init__(APIKey)
    
    async def get_by_key_hash(self, session: AsyncSession, key_hash: str) -> Optional[APIKey]:
        """根据key_hash获取API Key"""
        result = await session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()
    
    async def get_by_user_id(self, session: AsyncSession, user_id: str) -> List[APIKey]:
        """获取用户的所有API Key"""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_active_by_user_id(self, session: AsyncSession, user_id: str) -> List[APIKey]:
        """获取用户的所有活跃API Key"""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(APIKey.is_active == True)
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()
    
    async def update_last_used(self, session: AsyncSession, api_key_id: str) -> bool:
        """更新最后使用时间"""
        from datetime import datetime
        result = await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(last_used_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount > 0
    
    async def deactivate(self, session: AsyncSession, api_key_id: str) -> bool:
        """停用API Key"""
        result = await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(is_active=False)
        )
        await session.commit()
        return result.rowcount > 0
    
    async def get_by_user_and_name(self, session: AsyncSession, user_id: str, name: str) -> Optional[APIKey]:
        """根据用户ID和名称获取API Key"""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(APIKey.name == name)
        )
        return result.scalar_one_or_none()
    
    async def count_by_user(self, session: AsyncSession, user_id: str) -> int:
        """获取用户的API Key数量"""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(APIKey.is_active == True)
        )
        return len(result.scalars().all())
