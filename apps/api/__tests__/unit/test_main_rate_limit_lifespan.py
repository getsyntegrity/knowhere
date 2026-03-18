from types import SimpleNamespace
import sys

import pytest
from fastapi import FastAPI

import main as app_main


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMessagingService:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


async def _noop_async(*_args, **_kwargs):
    return None


def _patch_lifespan_dependencies(monkeypatch, load_rules_impl):
    import app.services.rate_limit.config as rate_limit_config_module
    import shared.core.database as database_module

    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_kw: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    monkeypatch.setattr(database_module, "prewarm_connection_pool", _noop_async)
    monkeypatch.setattr(database_module, "AsyncSessionFactory", lambda: _SessionContext())
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
    monkeypatch.setattr(app_main, "safe_dispose_engine", _noop_async)

    messaging = _FakeMessagingService()
    fake_messaging_module = SimpleNamespace(messaging_service=messaging)
    monkeypatch.setitem(
        sys.modules,
        "app.services.messaging_service",
        fake_messaging_module,
    )

    return messaging


@pytest.mark.asyncio
async def test_lifespan_initializes_and_tears_down_rate_limit_components(monkeypatch):
    load_calls: list[object] = []

    async def _fake_load_rules(db):
        load_calls.append(db)

    messaging = _patch_lifespan_dependencies(monkeypatch, _fake_load_rules)

    test_app = FastAPI()
    async with app_main.lifespan(test_app):
        assert hasattr(test_app.state, "rate_limit_rule_sync_task") is False
        assert len(load_calls) == 1
        assert messaging.start_calls == 1

    assert messaging.stop_calls == 1


@pytest.mark.asyncio
async def test_lifespan_fails_fast_when_initial_rule_load_fails(monkeypatch):
    async def _boom_load_rules(_db):
        raise RuntimeError("initial load failed")

    messaging = _patch_lifespan_dependencies(monkeypatch, _boom_load_rules)

    with pytest.raises(RuntimeError, match="initial load failed"):
        async with app_main.lifespan(FastAPI()):
            pass

    assert messaging.start_calls == 0
