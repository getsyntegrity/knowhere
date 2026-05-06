"""API key management service."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from app.repositories.api_key_repository import APIKeyRepository
from app.services.auth.api_key_identity_cache import api_key_identity_cache
from app.services.rate_limit.identity_cache import identity_cache
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.config import redis_pool_manager
from shared.core.database import get_db_context
from shared.core.exceptions.domain_exceptions import (
    APIKeyOperationException,
    KnowhereException,
    NotFoundException,
    ValidationException,
)
from shared.models.database.api_key import APIKey
from shared.models.database.user_balance import UserBalance
from shared.utils.api_keys import generate_api_key, hash_api_key, mask_api_key

_DEFAULT_USER_TIER: str = "free"
_API_KEY_MAX_CACHE_TTL_SECONDS: int = 3600


@dataclass(frozen=True)
class APIKeyIdentity:
    """Resolved identity for a validated API key."""

    user_id: str
    user_tier: str
    expires_at: datetime | None


class APIKeyService:
    """API key management service."""

    def __init__(self):
        self.repository = APIKeyRepository()

    def _mask_api_key(self, api_key: str) -> str:
        """Mask an API key, exposing only the first 8 and last 4 characters."""
        return mask_api_key(api_key)

    async def create_api_key(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        enabled_modules: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Create an API key."""
        key_count = await self.repository.count_by_user(session, user_id)
        if key_count >= 10:
            raise ValidationException(
                user_message="Maximum API Key limit reached (10)",
                violations=[
                    {
                        "field": "api_keys",
                        "description": "User has reached the maximum API Key limit",
                    }
                ],
            )

        existing_key = await self.repository.get_by_user_and_name(
            session, user_id, name
        )
        if existing_key:
            raise ValidationException(
                user_message="API Key name already exists",
                violations=[
                    {
                        "field": "name",
                        "description": f"An API Key with name '{name}' already exists",
                    }
                ],
            )

        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        key_mask = mask_api_key(api_key)

        api_key_record = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_mask=key_mask,
            name=name,
            enabled_modules=enabled_modules or ["all"],
            expires_at=expires_at,
        )

        await self.repository.create(session, api_key_record)

        return api_key

    async def get_identity(
        self,
        session: AsyncSession,
        api_key: str,
    ) -> APIKeyIdentity | None:
        """Return API-key identity, using auth cache before DB fallback."""
        key_hash: str = hash_api_key(api_key)
        cached_identity = await self._get_cached_identity(key_hash)
        if cached_identity is not None:
            return cached_identity

        identity = await self._get_database_identity(session, key_hash)
        if identity is None:
            return None

        await self._cache_api_key_identity(key_hash=key_hash, identity=identity)
        return identity

    async def _get_cached_identity(self, key_hash: str) -> APIKeyIdentity | None:
        """Return cached API-key user identity, or None on miss/cache failure."""
        user_id = await api_key_identity_cache.get_user_id(
            redis_pool_manager.get_redis_service(),
            key_hash,
        )
        if user_id is None:
            return None

        return APIKeyIdentity(
            user_id=user_id,
            user_tier=await self._get_user_tier(user_id),
            expires_at=None,
        )

    async def _get_database_identity(
        self,
        session: AsyncSession,
        key_hash: str,
    ) -> APIKeyIdentity | None:
        """Validate API key against the database."""
        api_key_record = await self.repository.get_by_key_hash(session, key_hash)

        if not api_key_record or not api_key_record.is_valid():
            return None

        self._schedule_last_used_update(str(api_key_record.id))
        user_id = str(api_key_record.user_id)
        user_tier = await self._resolve_user_tier_from_db(session, user_id)

        return APIKeyIdentity(
            user_id=user_id,
            user_tier=user_tier,
            expires_at=api_key_record.expires_at,
        )

    async def _cache_api_key_identity(
        self,
        *,
        key_hash: str,
        identity: APIKeyIdentity,
    ) -> None:
        """Cache the validated API-key user ID for the auth layer."""
        try:
            await api_key_identity_cache.set_user_id(
                redis_pool_manager.get_redis_service(),
                key_hash,
                identity.user_id,
                ttl_seconds=self._resolve_api_key_cache_ttl_seconds(
                    identity.expires_at
                ),
            )
        except Exception:
            logger.warning(
                "api_key_service: failed to cache identity for user_id={}",
                identity.user_id,
            )

    async def _get_user_tier(self, user_id: str) -> str:
        """Return user tier from rate-limit cache or DB fallback."""
        redis_service = redis_pool_manager.get_redis_service()
        cached_identity = await identity_cache.get_user_tier(redis_service, user_id)
        if cached_identity is not None:
            return cached_identity["user_tier"]

        async with get_db_context() as session:
            user_tier = await self._resolve_user_tier_from_db(session, user_id)
            await identity_cache.set_user_tier(redis_service, user_id, user_tier)
            return user_tier

    async def _resolve_user_tier_from_db(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> str:
        """Resolve the billing tier for the API key owner."""
        result = await session.execute(
            select(UserBalance.user_tier).where(UserBalance.user_id == user_id).limit(1)
        )
        user_tier = result.scalar_one_or_none()
        return str(user_tier) if user_tier is not None else _DEFAULT_USER_TIER

    def _resolve_api_key_cache_ttl_seconds(self, expires_at: datetime | None) -> int:
        """Resolve cache TTL for API-key identity without exceeding key expiry."""
        if expires_at is None:
            return _API_KEY_MAX_CACHE_TTL_SECONDS

        expires_at_utc = expires_at
        if expires_at_utc.tzinfo is None:
            expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        remaining_seconds = int((expires_at_utc - now).total_seconds())
        return max(1, min(_API_KEY_MAX_CACHE_TTL_SECONDS, remaining_seconds))

    async def revoke_api_key(
        self, session: AsyncSession, api_key_id: str, user_id: str
    ) -> bool:
        """Revoke an API key by deleting it directly."""
        logger.info(f"Revoking API key: api_key_id={api_key_id}, user_id={user_id}")

        api_key = await self.repository.get_by_id(session, api_key_id)

        if not api_key:
            logger.warning("API key does not exist")
            raise NotFoundException(
                resource="APIKey",
                resource_id=api_key_id,
                internal_message="API Key not found",
            )

        if str(api_key.user_id) != user_id:
            logger.warning(
                f"User ID mismatch: api_key.user_id={api_key.user_id}, user_id={user_id}"
            )
            raise NotFoundException(
                resource="APIKey",
                resource_id=api_key_id,
                internal_message="API Key not found or does not belong to user",
            )

        success = await self.repository.delete_by_id(session, api_key_id)
        logger.info(f"Delete result: {success}")

        if success:
            await session.commit()
            logger.info("Transaction committed")
            await self._invalidate_revoked_api_key_cache_best_effort(
                user_id=user_id,
                key_hash=api_key.key_hash,
            )

        return success

    # TODO, invalidate should not be best-effort
    async def _invalidate_revoked_api_key_cache_best_effort(
        self,
        user_id: str,
        key_hash: str,
    ) -> None:
        """Best-effort cache invalidation after a revoke has already been committed."""
        try:
            await api_key_identity_cache.invalidate_api_key(
                redis_pool_manager.get_redis_service(),
                user_id,
                key_hash,
            )
        except Exception as err:
            logger.warning(
                f"Failed to invalidate revoked API key cache (ignored): {err}"
            )

    async def list_user_api_keys(
        self, session: AsyncSession, user_id: str
    ) -> List[dict]:
        """List a user's API keys, including disabled ones that are still valid."""
        api_keys = await self.repository.get_unexpired_by_user_id(session, user_id)
        return [
            {
                "id": str(api_key.id),
                "name": api_key.name,
                "api_key": api_key.key_mask
                or f"sk_{api_key.id[:8]}••••••••••••••••••••••••••••••••••••••••",
                "enabled_modules": api_key.enabled_modules,
                "is_active": api_key.is_active,
                "created_at": api_key.created_at,
                "last_used_at": api_key.last_used_at,
                "expires_at": api_key.expires_at,
            }
            for api_key in api_keys
        ]

    def _schedule_last_used_update(self, api_key_id: str) -> None:
        """Schedule a best-effort background update for api_keys.last_used_at."""
        try:
            asyncio.create_task(
                self._update_last_used_best_effort(api_key_id),
                name=f"api_key_last_used:{api_key_id}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to schedule API key last-used update (ignored): {e}"
            )

    async def _update_last_used_best_effort(self, api_key_id: str) -> None:
        """Best-effort async update; failures are logged but never propagated."""
        try:
            async with get_db_context() as db:
                await self.repository.update_last_used(db, api_key_id)
        except Exception as e:
            logger.warning(f"Failed to update API key last-used time (ignored): {e}")

    async def get_api_key(
        self, session: AsyncSession, user_id: str, api_key_id: str
    ) -> Optional[APIKey]:
        """Get a single API key for a user."""
        try:
            api_key = await self.repository.get(session, api_key_id)
            if api_key and api_key.user_id == user_id:
                return api_key
            return None
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to get API key: {e}")
            raise APIKeyOperationException(
                internal_message=f"Failed to get API key: {str(e)}",
                original_exception=e,
            )

    async def toggle_api_key(
        self, session: AsyncSession, user_id: str, api_key_id: str
    ) -> bool:
        """Enable or disable an API key."""
        try:
            api_key = await self.repository.get(session, api_key_id)
            if not api_key or str(api_key.user_id) != user_id:
                return False

            api_key.is_active = not api_key.is_active
            await session.commit()
            await session.refresh(api_key)

            if not api_key.is_active:
                await api_key_identity_cache.invalidate_api_key(
                    redis_pool_manager.get_redis_service(),
                    user_id,
                    api_key.key_hash,
                )

            logger.info(
                f"API key status toggled successfully: {api_key_id}, new_status={api_key.is_active}"
            )
            return True
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to toggle API key status: {e}")
            await session.rollback()
            raise APIKeyOperationException(
                internal_message=f"Failed to toggle API key status: {str(e)}",
                original_exception=e,
            )
