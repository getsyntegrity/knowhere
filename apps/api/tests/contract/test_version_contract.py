from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_should_return_version_payload_for_the_v1_version_endpoint(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        response = await api_client.get("/api/v1/version")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())

    assert response_json["service"] == "knowhere-api"
    assert response_json["version"]
    assert "commit" in response_json
    assert "build_time" in response_json
    assert response_json["environment"] == "production"


@pytest.mark.asyncio
async def test_should_return_the_same_payload_from_the_v1_root_endpoint(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        version_response = await api_client.get("/api/v1/version")
        root_response = await api_client.get("/api/v1/")

    assert version_response.status_code == 200
    assert root_response.status_code == 200
    assert root_response.json() == version_response.json()
