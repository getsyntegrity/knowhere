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


class _FakeListener:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


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
    fake_redis_service = object()
    monkeypatch.setattr(
        app_main.redis_pool_manager,
        "get_redis_service",
        lambda: fake_redis_service,
    )
    monkeypatch.setattr(
        rate_limit_config_module.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls, *_args, **_kwargs: object()),
    )
    monkeypatch.setattr(app_main, "load_rules", load_rules_impl)
    monkeypatch.setattr(app_main.httpx, "AsyncClient", lambda **_kwargs: object())
    monkeypatch.setattr(app_main, "safe_dispose_engine", _noop_async)

    listener = _FakeListener()
    monkeypatch.setattr(app_main, "RateLimitPubSubListener", lambda _redis: listener)

    messaging = _FakeMessagingService()
    fake_messaging_module = SimpleNamespace(messaging_service=messaging)
    monkeypatch.setitem(
        sys.modules,
        "app.services.messaging_service",
        fake_messaging_module,
    )

    return listener, messaging, fake_redis_service


@pytest.mark.asyncio
async def test_lifespan_initializes_and_tears_down_rate_limit_components(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_RULE_SYNC_INTERVAL_SECONDS", "3600")
    load_calls: list[tuple[object, object, bool]] = []

    async def _fake_load_rules(db, redis_service, publish_updates=True):
        load_calls.append((db, redis_service, publish_updates))
        return False

    listener, messaging, fake_redis_service = _patch_lifespan_dependencies(
        monkeypatch,
        _fake_load_rules,
    )

    test_app = FastAPI()
    async with app_main.lifespan(test_app):
        assert listener.started is True
        assert hasattr(test_app.state, "pubsub_listener")
        assert hasattr(test_app.state, "rate_limit_rule_sync_task")
        assert test_app.state.pubsub_listener is listener
        assert test_app.state.rate_limit_rule_sync_task.done() is False
        assert len(load_calls) == 1
        assert load_calls[0][1] is fake_redis_service
        assert load_calls[0][2] is True
        assert messaging.start_calls == 1

    assert listener.stopped is True
    assert test_app.state.rate_limit_rule_sync_task.done() is True
    assert messaging.stop_calls == 1


@pytest.mark.asyncio
async def test_lifespan_fails_fast_when_initial_rule_load_fails(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_RULE_SYNC_INTERVAL_SECONDS", "3600")

    async def _boom_load_rules(_db, _redis_service, publish_updates=True):
        raise RuntimeError("initial load failed")

    listener, messaging, _ = _patch_lifespan_dependencies(monkeypatch, _boom_load_rules)

    with pytest.raises(RuntimeError, match="initial load failed"):
        async with app_main.lifespan(FastAPI()):
            pass

    # Fail-fast means startup aborts before listener/messaging startup.
    assert listener.started is False
    assert messaging.start_calls == 0
