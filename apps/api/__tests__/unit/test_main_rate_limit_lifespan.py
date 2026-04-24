from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import main as app_main


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _LifespanTracker:
    def __init__(self) -> None:
        self.close_async_client_calls: int = 0
        self.dispose_engine_calls: int = 0

    async def close_async_client(self) -> None:
        self.close_async_client_calls += 1

    async def dispose_engine(self, *_args: object, **_kwargs: object) -> None:
        self.dispose_engine_calls += 1


async def _noop_async(*_args: object, **_kwargs: object) -> None:
    return None


def _patch_lifespan_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    load_rules_impl: Callable[[object], Awaitable[None]],
) -> _LifespanTracker:
    import app.services.rate_limit.config as rate_limit_config_module
    import shared.core.database as database_module
    import shared.utils.http_clients as http_clients_module

    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_kw: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    monkeypatch.setattr(database_module, "prewarm_connection_pool", _noop_async)
    monkeypatch.setattr(
        database_module, "AsyncSessionFactory", lambda: _SessionContext()
    )
    monkeypatch.setattr(app_main.redis_pool_manager, "init_pool", _noop_async)
    monkeypatch.setattr(
        app_main.redis_pool_manager,
        "config",
        SimpleNamespace(get_connection_url=lambda: "redis://unused:6379/0"),
    )
    monkeypatch.setattr(
        rate_limit_config_module.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls, *_args, **_kwargs: object()),
    )
    monkeypatch.setattr(app_main, "load_rules", load_rules_impl)
    monkeypatch.setattr(app_main.httpx, "AsyncClient", lambda **_kwargs: object())
    tracker = _LifespanTracker()
    monkeypatch.setattr(app_main, "safe_dispose_engine", tracker.dispose_engine)
    monkeypatch.setattr(
        http_clients_module,
        "close_async_client",
        tracker.close_async_client,
    )

    return tracker


@pytest.mark.asyncio
async def test_lifespan_initializes_and_tears_down_rate_limit_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_calls: list[object] = []

    async def _fake_load_rules(db: object) -> None:
        load_calls.append(db)

    tracker = _patch_lifespan_dependencies(monkeypatch, _fake_load_rules)

    test_app = FastAPI()
    async with app_main.lifespan(test_app):
        assert hasattr(test_app.state, "rate_limit_rule_sync_task") is False
        assert len(load_calls) == 1
        assert tracker.close_async_client_calls == 0
        assert tracker.dispose_engine_calls == 0

    assert tracker.close_async_client_calls == 1
    assert tracker.dispose_engine_calls == 1


@pytest.mark.asyncio
async def test_lifespan_fails_fast_when_initial_rule_load_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom_load_rules(_db: object) -> None:
        raise RuntimeError("initial load failed")

    tracker = _patch_lifespan_dependencies(monkeypatch, _boom_load_rules)

    with pytest.raises(RuntimeError, match="initial load failed"):
        async with app_main.lifespan(FastAPI()):
            pass

    assert tracker.close_async_client_calls == 0
    assert tracker.dispose_engine_calls == 0
