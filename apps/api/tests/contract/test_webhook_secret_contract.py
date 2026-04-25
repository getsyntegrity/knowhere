from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_should_create_a_webhook_secret_and_return_the_full_secret_once(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    endpoint = f"https://example.test/hooks/{uuid4().hex[:8]}"

    async with developer_api_client_factory() as api_client:
        response = await api_client.post(
            "/api/v1/webhooks/secrets",
            json={"endpoint": endpoint},
        )

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())
    secret = cast(str, response_json["secret"])
    secret_masked = cast(str, response_json["secret_masked"])

    assert cast(str, response_json["id"]).startswith("ws_")
    assert response_json["endpoint"] == endpoint
    assert secret.startswith("whsec_")
    assert secret_masked.startswith("whsec_****")
    assert secret_masked.endswith(secret[-4:])
    assert response_json["status"] == "active"
    assert response_json["created_at"]


@pytest.mark.asyncio
async def test_should_return_an_existing_masked_webhook_secret_for_the_same_endpoint(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    endpoint = f"https://example.test/hooks/{uuid4().hex[:8]}"

    async with developer_api_client_factory() as api_client:
        first_response = await api_client.post(
            "/api/v1/webhooks/secrets",
            json={"endpoint": endpoint},
        )
        second_response = await api_client.post(
            "/api/v1/webhooks/secrets",
            json={"endpoint": endpoint},
        )
        list_response = await api_client.get("/api/v1/webhooks/secrets")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert list_response.status_code == 200

    first_response_json = cast(dict[str, object], first_response.json())
    second_response_json = cast(dict[str, object], second_response.json())
    list_response_json = cast(dict[str, object], list_response.json())
    secrets = cast(list[dict[str, object]], list_response_json["secrets"])

    assert second_response_json["id"] == first_response_json["id"]
    assert "secret" not in second_response_json
    assert second_response_json["secret_masked"] != first_response_json["secret"]
    assert list_response_json["total"] == 1
    assert secrets[0]["id"] == first_response_json["id"]
    assert "secret" not in secrets[0]
    assert cast(str, secrets[0]["secret_masked"]).startswith("whsec_")


@pytest.mark.asyncio
async def test_should_revoke_a_webhook_secret(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        create_response = await api_client.post(
            "/api/v1/webhooks/secrets",
            json={},
        )
        create_response_json = cast(dict[str, object], create_response.json())
        secret_id = cast(str, create_response_json["id"])

        delete_response = await api_client.delete(f"/api/v1/webhooks/secrets/{secret_id}")
        list_response = await api_client.get("/api/v1/webhooks/secrets")

    assert delete_response.status_code == 200
    assert delete_response.json() == {
        "status": "revoked",
        "id": secret_id,
    }

    list_response_json = cast(dict[str, object], list_response.json())
    secrets = cast(list[dict[str, object]], list_response_json["secrets"])

    assert list_response_json["total"] == 1
    assert secrets[0]["id"] == secret_id
    assert secrets[0]["status"] == "revoked"


@pytest.mark.asyncio
async def test_should_return_not_found_when_revoking_a_missing_webhook_secret(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    missing_secret_id = f"ws_{uuid4().hex[:24]}"

    async with developer_api_client_factory() as api_client:
        response = await api_client.delete(
            f"/api/v1/webhooks/secrets/{missing_secret_id}"
        )

    assert response.status_code == 404
    assert response.headers["x-request-id"]

    response_json = cast(dict[str, object], response.json())
    error = cast(dict[str, object], response_json["error"])

    assert response_json["success"] is False
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "WebhookSecret not found"
    assert error["details"] == {
        "resource": "WebhookSecret",
        "id": missing_secret_id,
    }
