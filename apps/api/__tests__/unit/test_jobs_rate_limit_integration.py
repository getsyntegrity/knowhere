from unittest.mock import AsyncMock

import pytest
from fastapi import Request

from app.api.v1.routes import jobs
from app.services.rate_limit.data_structures import CurrentUser
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)
from shared.models.schemas.job import JobCreate


def _make_http_request() -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/jobs",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RateLimitException(retry_after=5, limit=1, period="minute"),
        UnavailableException(
            internal_message="capacity check unavailable",
            retry_after=15,
        ),
    ],
)
async def test_create_job_reraises_capacity_errors(monkeypatch, error):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))
    enforcer = AsyncMock(side_effect=error)
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", enforcer)

    payload = JobCreate(source_type="file", file_name="doc.pdf")
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    with pytest.raises(type(error)):
        await jobs.create_job(
            payload=payload,
            http_request=_make_http_request(),
            current_user=current_user,
            db=object(),
        )

    assert enforcer.await_count == 1
