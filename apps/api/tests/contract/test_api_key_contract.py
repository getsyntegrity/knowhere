from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_should_revoke_a_created_api_key_through_http_only(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    create_payload: dict[str, object] = {
        "name": "contract-revocable-key",
        "enabled_modules": ["jobs"],
    }

    async with developer_api_client_factory() as api_client:
        create_response = await api_client.post("/api/v1/auth/create", json=create_payload)
        assert create_response.status_code == 200

        create_response_json = cast(dict[str, object], create_response.json())
        created_api_key = cast(str, create_response_json["api_key"])

        assert created_api_key.startswith("sk_")
        assert create_response_json["name"] == create_payload["name"]
        assert create_response_json["enabled_modules"] == create_payload["enabled_modules"]
        assert create_response_json["expires_at"] is None

        list_response = await api_client.get("/api/v1/auth/list")
        assert list_response.status_code == 200

        list_response_json = cast(dict[str, object], list_response.json())
        api_keys = cast(list[dict[str, object]], list_response_json["api_keys"])
        created_api_key_record = next(
            api_key
            for api_key in api_keys
            if api_key["name"] == create_payload["name"]
        )
        created_api_key_id = cast(str, created_api_key_record["id"])

        revoke_response = await api_client.post(
            "/api/v1/auth/revoke",
            json={"api_key_id": created_api_key_id},
        )
        assert revoke_response.status_code == 200
        assert revoke_response.json() == {"message": "API key revoked"}

        list_after_revoke_response = await api_client.get("/api/v1/auth/list")
        assert list_after_revoke_response.status_code == 200

        list_after_revoke_json = cast(
            dict[str, object], list_after_revoke_response.json()
        )
        api_keys_after_revoke = cast(
            list[dict[str, object]], list_after_revoke_json["api_keys"]
        )

        assert all(
            api_key["id"] != created_api_key_id for api_key in api_keys_after_revoke
        )

        api_client.headers.update({"Authorization": f"Bearer {created_api_key}"})
        rejected_response = await api_client.get("/api/v1/jobs")

    assert rejected_response.status_code == 401
    assert rejected_response.headers["x-request-id"]

    rejected_response_json = cast(dict[str, object], rejected_response.json())
    error = cast(dict[str, object], rejected_response_json["error"])

    assert rejected_response_json["success"] is False
    assert error["code"] == "UNAUTHENTICATED"
    assert error["message"] == "Invalid API Key"
    assert "details" not in error
