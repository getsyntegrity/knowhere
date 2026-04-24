"""API key repository."""

from datetime import datetime, timezone
from typing import Optional, Sequence

from app.repositories.base_repository import BaseRepository
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.api_key import APIKey


class APIKeyRepository(BaseRepository[APIKey, dict, dict]):
    """API key data access."""

    def __init__(self):
        super().__init__(APIKey)

    async def get_by_id(
        self, session: AsyncSession, api_key_id: str
    ) -> Optional[APIKey]:
        """Get an API key by ID."""
        result = await session.execute(select(APIKey).where(APIKey.id == api_key_id))
        return result.scalar_one_or_none()

    async def get_by_key_hash(
        self, session: AsyncSession, key_hash: str
    ) -> Optional[APIKey]:
        """Get an API key by key hash."""
        result = await session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self, session: AsyncSession, user_id: str
    ) -> Sequence[APIKey]:
        """Get all API keys for a user."""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()

    async def get_unexpired_by_user_id(
        self, session: AsyncSession, user_id: str
    ) -> Sequence[APIKey]:
        """Get all unexpired API keys for a user, including disabled ones."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(
                or_(
                    APIKey.expires_at.is_(None),  # Never expires.
                    APIKey.expires_at > now,  # Not expired yet.
                )
            )
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()

    async def get_active_by_user_id(
        self, session: AsyncSession, user_id: str
    ) -> Sequence[APIKey]:
        """Get all active API keys for a user."""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(APIKey.is_active == True)
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()

    async def update_last_used(self, session: AsyncSession, api_key_id: str) -> bool:
        """Update the last-used timestamp."""
        from datetime import datetime, timezone

        result = await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(last_used_at=datetime.now(timezone.utc).replace(tzinfo=None))
        )
        return result.rowcount > 0

    async def deactivate(self, session: AsyncSession, api_key_id: str) -> bool:
        """Deactivate an API key."""
        result = await session.execute(
            update(APIKey).where(APIKey.id == api_key_id).values(is_active=False)
        )
        return result.rowcount > 0

    async def delete_by_id(self, session: AsyncSession, api_key_id: str) -> bool:
        """Delete an API key."""
        result = await session.execute(delete(APIKey).where(APIKey.id == api_key_id))
        return result.rowcount > 0

    async def get_by_user_and_name(
        self, session: AsyncSession, user_id: str, name: str
    ) -> Optional[APIKey]:
        """Get an API key by user ID and name."""
        result = await session.execute(
            select(APIKey).where(APIKey.user_id == user_id).where(APIKey.name == name)
        )
        return result.scalar_one_or_none()

    async def count_by_user(self, session: AsyncSession, user_id: str) -> int:
        """Count active API keys for a user."""
        result = await session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(APIKey.is_active == True)
        )
        return len(result.scalars().all())
