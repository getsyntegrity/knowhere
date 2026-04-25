"""API key management service."""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from app.repositories.api_key_repository import APIKeyRepository
from app.services.rate_limit.identity_cache import identity_cache
from loguru import logger
from sqlalchemy import select
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

_DEFAULT_USER_TIER: str = "free"


@dataclass(frozen=True)
class APIKeyIdentity:
    """Resolved identity for a validated API key."""

    user_id: str
    user_tier: str


class APIKeyService:
    """API key management service."""

    def __init__(self):
        self.repository = APIKeyRepository()

    def _mask_api_key(self, api_key: str) -> str:
        """Mask an API key, exposing only the first 8 and last 4 characters."""
        if not api_key or len(api_key) < 12:
            return api_key
        return api_key[:8] + "•" * (len(api_key) - 12) + api_key[-4:]

    async def create_api_key(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        enabled_modules: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Create an API key."""
        # 1. Enforce the per-user API key limit.
        key_count = await self.repository.count_by_user(session, user_id)
        if key_count >= 10:  # Limit each user to at most 10 API keys.
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

        # 3. Generate a secure API key (sk_ + a 32-char UUID without hyphens).
        api_key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_mask = self._mask_api_key(api_key)

        # 4. Store it in the database.
        api_key_record = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_mask=key_mask,
            name=name,
            enabled_modules=enabled_modules
            or ["all"],  # Enable all modules by default.
            expires_at=expires_at,
        )

        await self.repository.create(session, api_key_record)

        return api_key

    async def validate_api_key(
        self, session: AsyncSession, api_key: str
    ) -> Optional[str]:
        """Validate API key against DB, return user_id or None."""
        identity = await self.validate_api_key_identity(session, api_key)
        return identity.user_id if identity is not None else None

    async def validate_api_key_identity(
        self,
        session: AsyncSession,
        api_key: str,
    ) -> Optional[APIKeyIdentity]:
        """Validate API key and return the authenticated identity."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_record = await self.repository.get_by_key_hash(session, key_hash)

        if not api_key_record or not api_key_record.is_valid():
            return None

        self._schedule_last_used_update(str(api_key_record.id))
        user_id = str(api_key_record.user_id)
        user_tier = await self._resolve_user_tier(session, user_id)

        return APIKeyIdentity(
            user_id=user_id,
            user_tier=user_tier,
        )

    async def _resolve_user_tier(
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

    async def revoke_api_key(
        self, session: AsyncSession, api_key_id: str, user_id: str
    ) -> bool:
        """Revoke an API key by deleting it directly."""
        logger.info(f"Revoking API key: api_key_id={api_key_id}, user_id={user_id}")

        # 1. Verify that the API key belongs to the user.
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

        # 2. Delete the API key directly.
        success = await self.repository.delete_by_id(session, api_key_id)
        logger.info(f"Delete result: {success}")

        # 3. Commit the transaction.
        if success:
            await session.commit()
            logger.info("Transaction committed")
            await self._invalidate_revoked_api_key_cache_best_effort(
                user_id=user_id,
                key_hash=api_key.key_hash,
            )

        return success

    async def _invalidate_revoked_api_key_cache_best_effort(
        self,
        user_id: str,
        key_hash: str,
    ) -> None:
        """Best-effort cache invalidation after a revoke has already been committed."""
        try:
            await identity_cache.invalidate_apikey(
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
                or f"sk_{api_key.id[:8]}••••••••••••••••••••••••••••••••••••••••",  # Return the masked API key.
                "enabled_modules": api_key.enabled_modules,
                "is_active": api_key.is_active,
                "created_at": api_key.created_at,
                "last_used_at": api_key.last_used_at,
                "expires_at": api_key.expires_at,
            }
            for api_key in api_keys
        ]

    async def regenerate_api_key(
        self, session: AsyncSession, api_key_id: str, user_id: str
    ) -> str:
        """Regenerate an API key."""
        api_key = await self.repository.get_by_id(session, api_key_id)
        if not api_key or api_key.user_id != user_id:
            raise NotFoundException(
                resource="APIKey",
                resource_id=api_key_id,
                internal_message="API Key not found or does not belong to user",
            )

        # 2. Generate a new API key (sk_ + a 32-char UUID without hyphens).
        new_api_key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
        new_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
        new_key_mask = self._mask_api_key(new_api_key)

        # 3. Update the database record.
        from sqlalchemy import update

        from shared.models.database.api_key import APIKey

        await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(
                key_hash=new_key_hash,
                key_mask=new_key_mask,
            )
        )
        await session.commit()

        # 4. Refresh the cache.
        await identity_cache.invalidate_apikey(
            redis_pool_manager.get_redis_service(),
            user_id,
            api_key.key_hash,
        )

        return new_api_key

    async def check_module_permission(
        self, session: AsyncSession, api_key: str, module: str
    ) -> bool:
        """Check whether an API key can access the requested module."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_record = await self.repository.get_by_key_hash(session, key_hash)

        if not api_key_record or not api_key_record.is_valid():
            return False

        # Allow access if all modules are enabled or the specific module is present.
        enabled_modules = api_key_record.enabled_modules or []
        return "all" in enabled_modules or module in enabled_modules

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
                await identity_cache.invalidate_apikey(
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
