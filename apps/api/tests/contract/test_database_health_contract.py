from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch


@pytest.mark.asyncio
async def test_should_return_the_database_health_payload_shape(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        response = await api_client.get("/api/v1/health/database/health")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())
    pool_status = cast(dict[str, object], response_json["pool_status"])

    assert response_json["status"] == "healthy"
    assert isinstance(response_json["response_time_ms"], float | int)
    assert response_json["last_check"]
    assert set(pool_status) == {
        "size",
        "checked_in",
        "checked_out",
        "overflow",
        "invalid",
    }


@pytest.mark.asyncio
async def test_should_sanitize_database_health_errors_before_returning_them(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
    monkeypatch: MonkeyPatch,
) -> None:
    async def _get_database_health() -> dict[str, object]:
        return {
            "status": "unhealthy",
            "error": "Database health check failed",
            "last_check": None,
        }

    async with api_client_factory() as api_client:
        from app.api.v1 import health as health_route_module

        monkeypatch.setattr(
            health_route_module,
            "get_database_health",
            _get_database_health,
        )
        response = await api_client.get("/api/v1/health/database/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unhealthy",
        "error": "Database health check failed",
        "last_check": None,
    }


@pytest.mark.asyncio
async def test_should_return_the_database_performance_payload_shape(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        from shared.core.database import db_performance_monitor

        db_performance_monitor.query_times = []
        db_performance_monitor.connection_usage = []
        db_performance_monitor.error_count = 0
        db_performance_monitor.record_query_time(3.2)
        db_performance_monitor.record_query_time(6.8)
        db_performance_monitor.record_connection_usage(
            {
                "checked_out": 1,
                "checked_in": 2,
                "overflow": 0,
            }
        )

        response = await api_client.get("/api/v1/health/database/performance")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())
    query_stats = cast(dict[str, object], response_json["query_stats"])
    connection_stats = cast(dict[str, object], response_json["connection_stats"])
    recent_usage = cast(list[dict[str, object]], connection_stats["recent_usage"])

    assert query_stats["count"] == 2
    assert isinstance(query_stats["avg_time_ms"], float)
    assert isinstance(query_stats["min_time_ms"], float)
    assert isinstance(query_stats["max_time_ms"], float)
    assert isinstance(query_stats["p95_time_ms"], float)
    assert connection_stats["total_errors"] == 0
    assert len(recent_usage) == 1


@pytest.mark.asyncio
async def test_should_return_the_database_prewarm_completion_message(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        response = await api_client.post("/api/v1/health/database/prewarm")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Database connection pool prewarming completed"
    }
