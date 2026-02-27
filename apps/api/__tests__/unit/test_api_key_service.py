from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.auth import api_key_service as api_key_service_module
from app.services.auth.api_key_service import APIKeyService


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
        service, "_get_cached_user_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        service.repository,
        "get_by_key_hash",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(service, "_cache_api_key", AsyncMock())

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
