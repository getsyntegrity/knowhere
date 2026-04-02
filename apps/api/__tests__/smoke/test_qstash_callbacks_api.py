"""
Smoke tests for public QStash callback endpoints.
"""
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_qstash_callback_uses_signature_validation_instead_of_authorization(
    client: AsyncClient,
) -> None:
    """
    QStash callbacks are public and should fail on signature validation,
    not on missing Authorization headers.
    """
    response = await client.post(
        "/api/v1/webhooks/qstash/callback",
        json={"sourceHeader": {}},
    )

    assert response.status_code == 401
    assert response.text == "Invalid signature"


@pytest.mark.asyncio
async def test_qstash_failure_callback_uses_signature_validation_instead_of_authorization(
    client: AsyncClient,
) -> None:
    """
    The failure callback follows the same public contract as the success callback.
    """
    response = await client.post(
        "/api/v1/webhooks/qstash/failure",
        json={"sourceHeader": {}},
    )

    assert response.status_code == 401
    assert response.text == "Invalid signature"
