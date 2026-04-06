from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dependencies as core_dependencies
from app.services.auth.api_key_service import APIKeyIdentity
from shared.core.exceptions.domain_exceptions import PermissionDeniedException


def make_request(path: str, authorization: str) -> Request:
    headers = [(b"authorization", authorization.encode())]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "root_path": "/api",
        "headers": headers,
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_get_current_user_id_allows_guest_api_key_for_jobs(monkeypatch) -> None:
    request = make_request("/v1/jobs", "Bearer sk_guest_jobs")
    identity = APIKeyIdentity(user_id="guest-user", user_tier="guest")

    monkeypatch.setattr(
        core_dependencies.redis_pool_manager,
        "get_redis_service",
        lambda: object(),
    )
    monkeypatch.setattr(
        core_dependencies.identity_cache,
        "get_cached_identity",
        AsyncMock(return_value=None),
    )
    validate_identity = AsyncMock(return_value=identity)
    mock_service = type(
        "MockAPIKeyService",
        (),
        {"validate_api_key_identity": validate_identity},
    )
    monkeypatch.setattr(core_dependencies, "APIKeyService", mock_service)

    user_id = await core_dependencies.get_current_user_id(
        request=request,
        authorization="Bearer sk_guest_jobs",
        db=cast(AsyncSession, object()),
    )

    assert user_id == "guest-user"


@pytest.mark.asyncio
async def test_get_current_user_id_rejects_guest_api_key_for_billing_from_cache(monkeypatch) -> None:
    request = make_request("/v1/billing", "Bearer sk_guest_billing")

    monkeypatch.setattr(
        core_dependencies.redis_pool_manager,
        "get_redis_service",
        lambda: object(),
    )
    monkeypatch.setattr(
        core_dependencies.identity_cache,
        "get_cached_identity",
        AsyncMock(
            return_value={
                "user_id": "guest-user",
                "user_tier": "guest",
            }
        ),
    )

    with pytest.raises(PermissionDeniedException):
        await core_dependencies.get_current_user_id(
            request=request,
            authorization="Bearer sk_guest_billing",
            db=cast(AsyncSession, object()),
        )
