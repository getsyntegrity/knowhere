"""API key management service."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

from app.repositories.api_key_repository import APIKeyRepository
from loguru import logger
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
from shared.utils.api_keys import generate_api_key, hash_api_key, mask_api_key

from shared.services.redis.redis_service import RedisService

_API_KEY_USER_CACHE_TTL_SECONDS: int = 3600


class APIKeyService:
    """API key management service."""

    _instance: "APIKeyService | None" = None

    def __new__(cls) -> "APIKeyService":
        """Return the singleton API-key service object."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "repository"):
            return
        self.repository = APIKeyRepository()

    @classmethod
    def get_instance(cls) -> "APIKeyService":
        """Return the singleton API-key service instance."""
        return cls()

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

    async def validate_api_key(
        self, session: AsyncSession, api_key: str
    ) -> Optional[str]:
        """Validate API key against DB, return user_id or None."""
        key_hash: str = hash_api_key(api_key)
        cached_user_id = await self._get_cached_user_id(
            redis_pool_manager.get_redis_service(),
            key_hash,
        )
        if cached_user_id is not None:
            return cached_user_id

        api_key_record = await self.repository.get_by_key_hash(session, key_hash)
        if not api_key_record or not api_key_record.is_valid():
            return None

        self._schedule_last_used_update(str(api_key_record.id))
        user_id = str(api_key_record.user_id)
        await self._set_cached_user_id(
            redis_pool_manager.get_redis_service(),
            key_hash,
            user_id,
            self._resolve_api_key_cache_ttl_seconds(api_key_record.expires_at),
        )
        return user_id

    @staticmethod
    def _get_user_id_key(api_key_hash: str) -> str:
        """Return the Redis key for an API-key hash to user ID lookup."""
        return f"api-key:user-id:{api_key_hash}"

    @staticmethod
    def _get_user_api_keys_key(user_id: str) -> str:
        """Return the Redis reverse-index key for a user's API-key hashes."""
        return f"api-key:user-hashes:{user_id}"

    async def _get_cached_user_id(
        self,
        redis_service: RedisService,
        api_key_hash: str,
    ) -> str | None:
        """Return cached API-key user ID or None on miss/cache failure."""
        try:
            raw_user_id = await redis_service.get(self._get_user_id_key(api_key_hash))
            return self._coerce_user_id(raw_user_id)
        except Exception:
            logger.warning("api_key_service: failed to read API-key user cache")
            return None

    async def _set_cached_user_id(
        self,
        redis_service: RedisService,
        api_key_hash: str,
        user_id: str,
        ttl_seconds: int,
    ) -> None:
        """Cache a validated API-key to user ID lookup."""
        effective_ttl_seconds = min(_API_KEY_USER_CACHE_TTL_SECONDS, ttl_seconds)
        user_id_key = self._get_user_id_key(api_key_hash)
        user_api_keys_key = self._get_user_api_keys_key(user_id)

        try:
            await redis_service.set(user_id_key, user_id, ttl=effective_ttl_seconds)
            await redis_service.sadd(user_api_keys_key, api_key_hash)
            reverse_ttl_seconds = await redis_service.ttl(user_api_keys_key)
            if (
                reverse_ttl_seconds in (-2, -1)
                or reverse_ttl_seconds < effective_ttl_seconds
            ):
                await redis_service.expire(user_api_keys_key, effective_ttl_seconds)
        except Exception:
            logger.warning(
                "api_key_service: failed to write API-key user cache for user_id={}",
                user_id,
            )

    async def _invalidate_cached_api_key_user_id(
        self,
        redis_service: RedisService,
        user_id: str,
        api_key_hash: str,
    ) -> None:
        """Delete one API-key to user ID cache entry."""
        try:
            await redis_service.delete(self._get_user_id_key(api_key_hash))
            await redis_service.srem(self._get_user_api_keys_key(user_id), api_key_hash)
        except Exception:
            logger.warning(
                "api_key_service: failed to invalidate API-key cache for user_id={}",
                user_id,
            )

    def _coerce_user_id(self, raw_user_id: object) -> str | None:
        """Return a typed user ID from current or legacy Redis values."""
        if isinstance(raw_user_id, str):
            try:
                parsed_user_id: object = json.loads(raw_user_id)
            except json.JSONDecodeError:
                return raw_user_id
        else:
            parsed_user_id = raw_user_id

        if isinstance(parsed_user_id, str):
            return parsed_user_id

        if isinstance(parsed_user_id, dict):
            legacy_user_id = parsed_user_id.get("user_id")
            if isinstance(legacy_user_id, str):
                return legacy_user_id

        return None

    def _resolve_api_key_cache_ttl_seconds(self, expires_at: datetime | None) -> int:
        """Resolve cache TTL for an API-key lookup without exceeding key expiry."""
        if expires_at is None:
            return _API_KEY_USER_CACHE_TTL_SECONDS

        expires_at_utc = expires_at
        if expires_at_utc.tzinfo is None:
            expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        remaining_seconds = int((expires_at_utc - now).total_seconds())
        return max(1, min(_API_KEY_USER_CACHE_TTL_SECONDS, remaining_seconds))

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
            await self._invalidate_cached_api_key_user_id(
                redis_pool_manager.get_redis_service(),
                user_id,
                api_key.key_hash,
            )

        return success

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
                await self._invalidate_cached_api_key_user_id(
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
