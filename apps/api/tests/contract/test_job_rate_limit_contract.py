import importlib
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support.runtime import (
    clear_application_modules,
    configure_contract_environment,
    get_contract_database_url,
    prepare_contract_storage,
    seed_contract_developer,
)

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_API_ROOT: Path = _REPO_ROOT / "apps" / "api"
_SHARED_ROOT: Path = _REPO_ROOT / "packages" / "shared-python"


def _ensure_import_paths() -> None:
    api_root_value = str(_API_ROOT)
    shared_root_value = str(_SHARED_ROOT)

    if api_root_value not in sys.path:
        sys.path.insert(0, api_root_value)

    if shared_root_value not in sys.path:
        sys.path.insert(0, shared_root_value)


async def _create_contract_engine() -> AsyncEngine:
    return create_async_engine(get_contract_database_url(), future=True)


async def _count_jobs() -> int:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text("SELECT COUNT(*) FROM jobs"))
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _set_local_developer_concurrency_limit(
    *,
    max_concurrent_jobs: int,
    rpm_limit: int = 60,
) -> None:
    engine = await _create_contract_engine()

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE tier_limits
                    SET max_concurrent_jobs = :max_concurrent_jobs,
                        rpm_limit = :rpm_limit
                    WHERE tier_name = :tier_name
                    """
                ),
                {
                    "max_concurrent_jobs": max_concurrent_jobs,
                    "rpm_limit": rpm_limit,
                    "tier_name": "tier_5",
                },
            )
    finally:
        await engine.dispose()


@asynccontextmanager
async def _create_rate_limited_developer_api_client(
    monkeypatch: MonkeyPatch,
    *,
    max_concurrent_jobs: int,
) -> AsyncGenerator[AsyncClient, None]:
    configure_contract_environment(monkeypatch)
    await prepare_contract_storage()
    await _set_local_developer_concurrency_limit(
        max_concurrent_jobs=max_concurrent_jobs
    )
    _ensure_import_paths()
    clear_application_modules()

    api_module: ModuleType = importlib.import_module("main")
    app = api_module.app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            developer_profile = await seed_contract_developer()
            client.headers.update(
                {"Authorization": f"Bearer {str(developer_profile['api_key'])}"}
            )
            yield client


@pytest.mark.asyncio
async def test_should_return_too_many_requests_when_the_authenticated_user_exceeds_their_concurrent_job_limit(
    monkeypatch: MonkeyPatch,
) -> None:
    first_payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "file_name": "contract-rate-limit-first.pdf",
        "data_id": "contract-job-rate-limit-first",
    }
    second_payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "file_name": "contract-rate-limit-second.pdf",
        "data_id": "contract-job-rate-limit-second",
    }

    async with _create_rate_limited_developer_api_client(
        monkeypatch,
        max_concurrent_jobs=1,
    ) as api_client:
        first_response = await api_client.post("/api/v1/jobs", json=first_payload)
        second_response = await api_client.post("/api/v1/jobs", json=second_payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["x-request-id"]
    assert second_response.headers["retry-after"] == "30"
    assert second_response.headers["x-ratelimit-limit"] == "1"
    assert second_response.headers["x-ratelimit-period"] == "concurrent"

    response_json = cast(dict[str, object], second_response.json())
    error = cast(dict[str, object], response_json["error"])
    details = cast(dict[str, object], error["details"])

    assert response_json["success"] is False
    assert error["code"] == "RESOURCE_EXHAUSTED"
    assert (
        error["message"]
        == "Too many concurrent requests (1/1 active). Please retry after 30 seconds."
    )
    assert details == {
        "reason": "RATE_LIMIT_EXCEEDED",
        "retry_after": 30,
        "limit": 1,
        "period": "concurrent",
        "active_jobs": 1,
        "available_slots": 0,
    }
    assert await _count_jobs() == 1
