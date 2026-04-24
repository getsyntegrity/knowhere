from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support.runtime import get_contract_database_url


async def _create_contract_engine() -> AsyncEngine:
    return create_async_engine(get_contract_database_url(), future=True)


@pytest.mark.asyncio
async def test_should_create_a_new_guest_device_when_posting_a_fresh_device_id(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    payload: dict[str, str] = {
        "device_id": f"contract-guest-{uuid4().hex[:12]}",
        "client": "knowhere-hub",
        "platform": "macos",
        "app_version": "1.0.0",
    }

    async with api_client_factory() as api_client:
        response = await api_client.post("/api/v1/guest", json=payload)

    assert response.status_code == 200

    response_json: dict[str, object] = response.json()
    guest_user_id = str(response_json["guest_user_id"])

    assert response_json["device_id"] == payload["device_id"]
    assert str(response_json["api_key"]).startswith("sk_")
    assert response_json["expires_at"] is None
    assert response_json["rate_limit"] == {
        "rpm": 20,
        "daily_quota": -1,
        "max_concurrent_jobs": 10,
    }

    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            user_row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, name, email
                        FROM "user"
                        WHERE id = :user_id
                        """
                    ),
                    {"user_id": guest_user_id},
                )
            ).mappings().one()
            balance_row = (
                await connection.execute(
                    text(
                        """
                        SELECT user_tier
                        FROM user_balances
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": guest_user_id},
                )
            ).mappings().one()
            api_key_row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, is_active
                        FROM api_keys
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": guest_user_id},
                )
            ).mappings().one()
            guest_device_row = (
                await connection.execute(
                    text(
                        """
                        SELECT device_id, user_id, api_key_id, client, platform, app_version
                        FROM guest_devices
                        WHERE device_id = :device_id
                        """
                    ),
                    {"device_id": payload["device_id"]},
                )
            ).mappings().one()
    finally:
        await engine.dispose()

    assert user_row["name"] == f"Guest {payload['device_id']}"
    assert str(user_row["email"]).startswith("guest+")
    assert str(user_row["email"]).endswith("@guest.knowhere.local")
    assert balance_row["user_tier"] == "guest"
    assert api_key_row["is_active"] is True
    assert guest_device_row["user_id"] == guest_user_id
    assert guest_device_row["api_key_id"] == api_key_row["id"]
    assert guest_device_row["client"] == payload["client"]
    assert guest_device_row["platform"] == payload["platform"]
    assert guest_device_row["app_version"] == payload["app_version"]


@pytest.mark.asyncio
async def test_should_return_conflict_when_posting_an_existing_guest_device_id(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    payload: dict[str, str] = {
        "device_id": f"contract-guest-{uuid4().hex[:12]}",
        "client": "knowhere-hub",
        "platform": "macos",
        "app_version": "1.0.0",
    }

    async with api_client_factory() as api_client:
        first_response = await api_client.post("/api/v1/guest", json=payload)
        second_response = await api_client.post("/api/v1/guest", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409

    response_json: dict[str, object] = second_response.json()
    error = cast(dict[str, object], response_json["error"])

    assert response_json["success"] is False
    assert error["code"] == "ALREADY_EXISTS"
    assert error["details"] == {
        "reason": "ALREADY_EXISTS",
        "resource": "GuestDevice",
    }
    assert error["request_id"]
