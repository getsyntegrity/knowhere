from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.auth import api_key_service as api_key_service_module
from app.services.auth.api_key_service import APIKeyService
from shared.core.exceptions.domain_exceptions import NotFoundException


class _DBContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_validate_api_key_schedules_last_used_update(monkeypatch):
    service = APIKeyService()
    session = AsyncMock()
    record = SimpleNamespace(
        id="api_key_id_1",
        user_id="user_1",
        is_valid=lambda: True,
    )

    monkeypatch.setattr(
        service.repository,
        "get_by_key_hash",
        AsyncMock(return_value=record),
    )

    scheduled: list[str] = []
    monkeypatch.setattr(
        service,
        "_schedule_last_used_update",
        lambda api_key_id: scheduled.append(api_key_id),
    )

    user_id = await service.validate_api_key(session, "sk_test_token")

    assert user_id == "user_1"
    assert scheduled == ["api_key_id_1"]


@pytest.mark.asyncio
async def test_update_last_used_best_effort_swallows_errors(monkeypatch):
    service = APIKeyService()
    fake_db = object()

    monkeypatch.setattr(
        api_key_service_module,
        "get_db_context",
        lambda: _DBContext(fake_db),
    )
    monkeypatch.setattr(
        service.repository,
        "update_last_used",
        AsyncMock(side_effect=RuntimeError("db write failed")),
    )

    await service._update_last_used_best_effort("api_key_id_2")

    service.repository.update_last_used.assert_awaited_once_with(
        fake_db, "api_key_id_2"
    )


@pytest.mark.asyncio
async def test_revoke_api_key_commits_and_invalidates_cache(monkeypatch):
    service = APIKeyService()
    session = AsyncMock()
    api_key_record = SimpleNamespace(
        id="api_key_id_3",
        user_id="user_3",
        key_hash="key_hash_3",
    )
    redis_service = object()
    invalidate_apikey = AsyncMock()

    monkeypatch.setattr(
        service.repository,
        "get_by_id",
        AsyncMock(return_value=api_key_record),
    )
    monkeypatch.setattr(
        service.repository,
        "delete_by_id",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        api_key_service_module.redis_pool_manager,
        "get_redis_service",
        lambda: redis_service,
    )
    monkeypatch.setattr(
        api_key_service_module.identity_cache,
        "invalidate_apikey",
        invalidate_apikey,
    )

    success = await service.revoke_api_key(session, "api_key_id_3", "user_3")

    assert success is True
    session.commit.assert_awaited_once_with()
    invalidate_apikey.assert_awaited_once_with(
        redis_service,
        "user_3",
        "key_hash_3",
    )


@pytest.mark.asyncio
async def test_revoke_api_key_raises_not_found_when_missing(monkeypatch):
    service = APIKeyService()
    session = AsyncMock()

    monkeypatch.setattr(
        service.repository,
        "get_by_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(NotFoundException) as exc_info:
        await service.revoke_api_key(session, "missing_api_key", "user_4")

    assert exc_info.value.details == {"resource": "APIKey", "id": "missing_api_key"}


@pytest.mark.asyncio
async def test_revoke_api_key_ignores_cache_invalidation_errors(monkeypatch):
    service = APIKeyService()
    session = AsyncMock()
    api_key_record = SimpleNamespace(
        id="api_key_id_5",
        user_id="user_5",
        key_hash="key_hash_5",
    )

    monkeypatch.setattr(
        service.repository,
        "get_by_id",
        AsyncMock(return_value=api_key_record),
    )
    monkeypatch.setattr(
        service.repository,
        "delete_by_id",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        api_key_service_module.identity_cache,
        "invalidate_apikey",
        AsyncMock(side_effect=RuntimeError("redis unavailable")),
    )
    monkeypatch.setattr(
        api_key_service_module.redis_pool_manager,
        "get_redis_service",
        lambda: object(),
    )

    success = await service.revoke_api_key(session, "api_key_id_5", "user_5")

    assert success is True
    session.commit.assert_awaited_once_with()
