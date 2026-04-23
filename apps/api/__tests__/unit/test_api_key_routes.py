from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from shared.core.exceptions.domain_exceptions import NotFoundException


def assert_error_response(response_json: dict, expected_code: str) -> None:
    assert response_json.get("success") is False
    assert response_json["error"]["code"] == expected_code
    assert "request_id" in response_json["error"]


@pytest.mark.asyncio
async def test_revoke_api_key_returns_success(authenticated_client: AsyncClient) -> None:
    with patch("app.api.v1.routes.api_key.APIKeyService") as mock_api_key_service_class:
        mock_api_key_service = mock_api_key_service_class.return_value
        mock_api_key_service.revoke_api_key = AsyncMock(return_value=True)

        response = await authenticated_client.post(
            "/api/v1/auth/revoke",
            json={"api_key_id": "api_key_id_1"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "API key revoked"}


@pytest.mark.asyncio
async def test_revoke_api_key_returns_not_found(authenticated_client: AsyncClient) -> None:
    with patch("app.api.v1.routes.api_key.APIKeyService") as mock_api_key_service_class:
        mock_api_key_service = mock_api_key_service_class.return_value
        mock_api_key_service.revoke_api_key = AsyncMock(
            side_effect=NotFoundException(
                resource="APIKey",
                resource_id="missing_api_key",
            )
        )

        response = await authenticated_client.post(
            "/api/v1/auth/revoke",
            json={"api_key_id": "missing_api_key"},
        )

    assert response.status_code == 404
    assert_error_response(response.json(), "NOT_FOUND")
