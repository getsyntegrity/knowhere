from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.guest.guest_registration_service import GuestRegistrationService
from shared.core.exceptions.domain_exceptions import ConflictException, UnavailableException
from shared.models.database.user import User
from shared.models.schemas.guest import GuestRateLimitInfo


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
    device_id = "guest-registration-test-device"

    monkeypatch.setattr(
        service._credits_service,
        "ensure_user_initialized",
        AsyncMock(),
    )

    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service,
        "_get_guest_rate_limit_info",
        MagicMock(
            return_value=GuestRateLimitInfo(
                rpm=20,
                daily_quota=-1,
                max_concurrent_jobs=10,
            )
        ),
    )
    session.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: "api_key_id_123",
    )

    response = await service.register_guest(
        session=session,
        device_id=device_id,
        client="knowhere-hub",
        platform="macos",
        app_version="guest-registration-test",
    )

    created_user = session.add.call_args_list[0].args[0]

    assert isinstance(created_user, User)
    assert created_user.name == "Guest guest-registration-test-device"
    assert created_user.email.startswith("guest+")
    assert created_user.email.endswith("@guest.knowhere.local")
    assert response.device_id == device_id
    assert response.api_key.startswith("sk_")
    assert response.expires_at is None
    session.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_register_guest_rejects_existing_device_id(monkeypatch) -> None:
    service = GuestRegistrationService()
    session = create_mock_session()
    existing_device = SimpleNamespace(device_id="device-123")

    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id",
        AsyncMock(return_value=existing_device),
    )
    locked_lookup = AsyncMock(return_value=existing_device)
    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id_for_update",
        locked_lookup,
    )

    with pytest.raises(ConflictException) as exc_info:
        await service.register_guest(
            session=session,
            device_id="device-123",
            client="knowhere-hub",
            platform="macos",
            app_version="1.0.0",
        )

    assert exc_info.value.details == {
        "reason": "ALREADY_EXISTS",
        "resource": "GuestDevice",
    }
    locked_lookup.assert_awaited_once_with(session, "device-123")
    session.commit.assert_not_awaited()


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
    monkeypatch.setattr(
        service._credits_service,
        "ensure_user_initialized",
        AsyncMock(),
    )
    monkeypatch.setattr(
        service,
        "_get_guest_rate_limit_info",
        MagicMock(
            return_value=GuestRateLimitInfo(
                rpm=20,
                daily_quota=-1,
                max_concurrent_jobs=10,
            )
        ),
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
async def test_register_guest_conflicts_when_concurrent_create_loses_race(monkeypatch) -> None:
    service = GuestRegistrationService()
    session = create_mock_session()
    existing_device = SimpleNamespace(device_id="device-123")
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
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service._credits_service,
        "ensure_user_initialized",
        AsyncMock(),
    )
    monkeypatch.setattr(
        service,
        "_get_guest_rate_limit_info",
        MagicMock(
            return_value=GuestRateLimitInfo(
                rpm=20,
                daily_quota=-1,
                max_concurrent_jobs=10,
            )
        ),
    )
    locked_lookup = AsyncMock(return_value=existing_device)
    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id_for_update",
        locked_lookup,
    )
    session.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: "api_key_id_new",
    )
    session.commit.side_effect = conflict_error

    with pytest.raises(ConflictException) as exc_info:
        await service.register_guest(
            session=session,
            device_id="device-123",
            client="knowhere-hub",
            platform="macos",
            app_version="1.0.0",
        )

    assert exc_info.value.details == {
        "reason": "ALREADY_EXISTS",
        "resource": "GuestDevice",
    }
    session.rollback.assert_awaited_once_with()
    locked_lookup.assert_awaited_once_with(session, "device-123")


@pytest.mark.asyncio
async def test_register_guest_fails_before_commit_when_guest_rate_limit_missing(
    monkeypatch,
) -> None:
    service = GuestRegistrationService()
    session = create_mock_session()

    monkeypatch.setattr(
        service._device_repo,
        "get_by_device_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service,
        "_get_guest_rate_limit_info",
        MagicMock(side_effect=UnavailableException(
            internal_message="Guest tier limits are not loaded in RateLimitConfig",
            retry_after=60,
        )),
    )

    with pytest.raises(UnavailableException) as exc_info:
        await service.register_guest(
            session=session,
            device_id="device-456",
            client="knowhere-hub",
            platform="macos",
            app_version="1.0.0",
        )

    assert exc_info.value.retry_after == 60
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
