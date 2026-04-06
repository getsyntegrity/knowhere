from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.guest.guest_registration_service import GuestRegistrationService
from shared.models.database.user import User
from shared.models.schemas.guest import GuestRateLimitInfo, GuestRegisterResponse


def create_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_register_guest_assigns_name_when_creating_guest(monkeypatch) -> None:
    service = GuestRegistrationService()
    session = create_mock_session()
    device_id = "codex-staging-smoke-20260406"

    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id",
        AsyncMock(return_value=None),
    )
    session.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: "api_key_id_123",
    )

    response = await service.register_guest(
        session=session,
        device_id=device_id,
        client="knowhere-hub",
        platform="macos",
        app_version="codex-smoke",
    )

    created_user = session.add.call_args_list[0].args[0]

    assert isinstance(created_user, User)
    assert created_user.name == "Guest codex-staging-smoke-20260406"
    assert response.device_id == device_id
    assert response.api_key.startswith("sk_")
    session.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_register_guest_reraises_non_race_integrity_errors(monkeypatch) -> None:
    service = GuestRegistrationService()
    session = create_mock_session()
    error = IntegrityError(
        'INSERT INTO "user" (id, name, email) VALUES ($1, $2, $3)',
        {},
        Exception('null value in column "name" of relation "user" violates not-null constraint'),
    )

    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id",
        AsyncMock(return_value=None),
    )
    session.flush.side_effect = error

    with pytest.raises(IntegrityError):
        await service.register_guest(
            session=session,
            device_id="device-123",
            client="knowhere-hub",
            platform="macos",
            app_version="1.0.0",
        )

    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_guest_retries_when_device_id_conflict_wins_race(monkeypatch) -> None:
    service = GuestRegistrationService()
    session = create_mock_session()
    existing_device = SimpleNamespace(
        device_id="device-123",
        user_id="user-123",
        api_key_id="api_key_id_123",
    )
    expected_response = GuestRegisterResponse(
        guest_user_id="user-123",
        device_id="device-123",
        api_key="sk_existing",
        rate_limit=GuestRateLimitInfo(rpm=-1, daily_quota=-1, max_concurrent_jobs=10),
        expires_at=datetime.utcnow(),
    )
    conflict_error = IntegrityError(
        "INSERT INTO guest_devices (device_id) VALUES ($1)",
        {},
        Exception(
            'duplicate key value violates unique constraint "ix_guest_devices_device_id" '
            "DETAIL: Key (device_id)=(device-123) already exists."
        ),
    )

    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id",
        AsyncMock(side_effect=[None, existing_device]),
    )
    monkeypatch.setattr(
        service,
        "_reissue_key",
        AsyncMock(return_value=expected_response),
    )
    session.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: "api_key_id_new",
    )
    session.commit.side_effect = conflict_error

    response = await service.register_guest(
        session=session,
        device_id="device-123",
        client="knowhere-hub",
        platform="macos",
        app_version="1.0.0",
    )

    assert response == expected_response
    session.rollback.assert_awaited_once_with()
    service._reissue_key.assert_awaited_once()
