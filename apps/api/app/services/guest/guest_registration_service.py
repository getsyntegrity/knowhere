"""Guest registration business logic."""
from datetime import datetime, timedelta
from uuid import uuid4

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.guest_device_repository import GuestDeviceRepository
from app.services.auth.api_key_service import APIKeyService
from app.services.rate_limit.config import RateLimitConfig
from app.services.rate_limit.data_structures import TierLimits
from shared.models.database.guest_device import GuestDevice
from shared.models.database.user import User
from shared.models.database.user_balance import UserBalance
from shared.models.schemas.guest import (
    GuestRateLimitInfo,
    GuestRegisterResponse,
)

_GUEST_TIER: str = "guest"
_GUEST_KEY_EXPIRY_DAYS: int = 60
_GUEST_KEY_NAME_PREFIX: str = "guest-device"


class GuestRegistrationService:
    """Handles guest device registration and API key issuance."""

    def __init__(self) -> None:
        self._device_repo = GuestDeviceRepository()
        self._api_key_service = APIKeyService()

    async def register_guest(
        self,
        session: AsyncSession,
        device_id: str,
        client: str,
        platform: str,
        app_version: str | None,
    ) -> GuestRegisterResponse:
        """Register or re-register a guest device.

        - If the device_id already exists, revoke the old key and issue a new one.
        - If the device_id is new, create a guest user + API key + device record.
        - Handles concurrent first-registration race via IntegrityError retry.
        """
        expires_at = datetime.utcnow() + timedelta(days=_GUEST_KEY_EXPIRY_DAYS)
        key_name = f"{_GUEST_KEY_NAME_PREFIX}-{device_id[:32]}"

        existing = await self._device_repo.get_by_device_id(session, device_id)

        if existing is not None:
            # Lock the row to serialize concurrent reissue requests for the
            # same device_id.  Without this, two parallel requests could both
            # mint replacement keys, leaving multiple active credentials.
            locked = await self._device_repo.get_by_device_id_for_update(session, device_id)
            if locked is not None:
                return await self._reissue_key(session, locked, key_name, expires_at)

        try:
            return await self._create_new_guest(
                session, device_id, client, platform, app_version, key_name, expires_at
            )
        except IntegrityError:
            # Concurrent registration race: another request inserted this
            # device_id first.  Roll back our partial work and re-issue
            # against the winning row.
            await session.rollback()
            logger.info(
                "Concurrent guest registration detected, retrying as re-issue: device_id={}",
                device_id,
            )
            existing = await self._device_repo.get_by_device_id(session, device_id)
            if existing is None:
                raise
            return await self._reissue_key(session, existing, key_name, expires_at)

    async def _reissue_key(
        self,
        session: AsyncSession,
        device: GuestDevice,
        key_name: str,
        expires_at: datetime,
    ) -> GuestRegisterResponse:
        """Revoke old guest key and issue a fresh one.

        All mutations happen via direct SQL within a single transaction.
        We avoid calling ``APIKeyService.revoke_api_key()`` and
        ``create_api_key()`` because they commit internally — which would
        break atomicity and leave ``guest_devices.api_key_id`` dangling
        if a later step fails.
        """
        from sqlalchemy import delete, select

        from shared.models.database.api_key import APIKey

        user_id = device.user_id

        # 1. Delete old key (if any) directly — no intermediate commit.
        #    Fetch the key_hash first for cache invalidation later.
        old_api_key_hash: str | None = None
        if device.api_key_id:
            hash_result = await session.execute(
                select(APIKey.key_hash).where(APIKey.id == device.api_key_id).limit(1)
            )
            old_api_key_hash = hash_result.scalar_one_or_none()
            await session.execute(
                delete(APIKey).where(APIKey.id == device.api_key_id)
            )

        # 2. Create replacement key — flush only.
        api_key = await self._create_api_key_without_commit(
            session, user_id, key_name, expires_at
        )

        # 3. Link new key to device row — flush only.
        new_key_id = await self._resolve_api_key_id(session, api_key)
        if new_key_id:
            await self._device_repo.update_api_key(
                session, device.device_id, new_key_id
            )

        # 4. Single commit: old key gone, new key + device link persisted.
        await session.commit()

        # Best-effort cache invalidation for the deleted key.
        if old_api_key_hash is not None:
            try:
                from shared.core.config import redis_pool_manager
                from app.services.rate_limit.identity_cache import identity_cache

                await identity_cache.invalidate_apikey(
                    redis_pool_manager.get_redis_service(),
                    user_id,
                    old_api_key_hash,
                )
            except Exception as err:
                logger.warning("Failed to invalidate old guest key cache (ignored): {}", err)

        logger.info(
            "Re-issued guest API key: device_id={}, user_id={}",
            device.device_id,
            user_id,
        )
        return self._build_response(user_id, device.device_id, api_key, expires_at)

    async def _create_new_guest(
        self,
        session: AsyncSession,
        device_id: str,
        client: str,
        platform: str,
        app_version: str | None,
        key_name: str,
        expires_at: datetime,
    ) -> GuestRegisterResponse:
        """Create a brand-new guest user, API key, and device record.

        Everything is flushed (not committed) until the device row — which
        carries the unique device_id constraint — is inserted.  A single
        commit at the end ensures atomicity: if the device insert fails
        (e.g. concurrent race) the user/balance/key are rolled back too.
        """
        user_id = str(uuid4())

        user = User(id=user_id)
        session.add(user)

        balance = UserBalance(user_id=user_id, user_tier=_GUEST_TIER)
        session.add(balance)

        await session.flush()

        api_key = await self._create_api_key_without_commit(
            session, user_id, key_name, expires_at
        )

        api_key_id = await self._resolve_api_key_id(session, api_key)

        device = GuestDevice(
            device_id=device_id,
            user_id=user_id,
            api_key_id=api_key_id,
            client=client,
            platform=platform,
            app_version=app_version,
        )
        session.add(device)
        await session.commit()

        logger.info(
            "Created guest: device_id={}, user_id={}", device_id, user_id
        )
        return self._build_response(user_id, device_id, api_key, expires_at)

    async def _create_api_key_without_commit(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        expires_at: datetime,
    ) -> str:
        """Generate an API key record and flush (but do not commit).

        This avoids the internal commit inside APIKeyService.create_api_key()
        which would make the key durable before the device row is inserted.
        """
        import hashlib
        import uuid

        from shared.models.database.api_key import APIKey

        api_key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_mask = self._api_key_service._mask_api_key(api_key)

        api_key_record = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_mask=key_mask,
            name=name,
            enabled_modules=["guest"],
            expires_at=expires_at,
        )
        session.add(api_key_record)
        await session.flush()

        return api_key

    def _build_response(
        self,
        user_id: str,
        device_id: str,
        api_key: str,
        expires_at: datetime,
    ) -> GuestRegisterResponse:
        """Assemble the registration response with rate-limit metadata."""
        rate_limit = self._get_guest_rate_limit_info()
        return GuestRegisterResponse(
            guest_user_id=user_id,
            device_id=device_id,
            api_key=api_key,
            rate_limit=rate_limit,
            expires_at=expires_at,
        )

    @staticmethod
    def _get_guest_rate_limit_info() -> GuestRateLimitInfo:
        """Read guest tier limits from the live config."""
        try:
            config = RateLimitConfig.get_instance()
            tier: TierLimits | None = config.tier_map.get(_GUEST_TIER)
            if tier is not None:
                return GuestRateLimitInfo(
                    rpm=tier.rpm_limit,
                    daily_quota=tier.daily_quota,
                    max_concurrent_jobs=tier.max_concurrent_jobs,
                )
        except Exception:
            pass
        return GuestRateLimitInfo(rpm=-1, daily_quota=-1, max_concurrent_jobs=10)

    @staticmethod
    async def _resolve_api_key_id(session: AsyncSession, api_key: str) -> str | None:
        """Resolve the DB id for a just-created API key by its hash."""
        import hashlib
        from sqlalchemy import select
        from shared.models.database.api_key import APIKey

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await session.execute(
            select(APIKey.id).where(APIKey.key_hash == key_hash).limit(1)
        )
        return result.scalar_one_or_none()
