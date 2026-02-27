"""Tests for the RateLimitPubSubListener background task."""

import asyncio
import json

import pytest

from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits
from app.services.rate_limit.pubsub_listener import RateLimitPubSubListener
from app.services.rate_limit.rule_loader import (
    ACTIVE_RULES_KEY,
    RATE_LIMIT_UPDATES_CHANNEL,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_SNAPSHOT: dict = {
    "tier_map": {
        "free": {"rpm_limit": 2, "max_concurrent_jobs": 2, "daily_quota": 20},
        "tier_1": {"rpm_limit": 15, "max_concurrent_jobs": 5, "daily_quota": -1},
    },
    "system_rules": [
        {"method": "POST", "api_pattern": "/v1/jobs", "priority": 100, "rpm": 30},
        {"method": "*", "api_pattern": "*", "priority": 9999, "rpm": 1000},
    ],
}


class _FakePubSub:
    """In-memory Pub/Sub stub that delivers pre-loaded messages."""

    def __init__(self, messages: list[dict | None]) -> None:
        self._messages = list(messages)
        self.subscribed_channels: list[str] = []
        self.unsubscribed_channels: list[str] = []
        self._closed: bool = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_channels.append(channel)

    async def close(self) -> None:
        self._closed = True

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 0):
        if not self._messages:
            # Yield control so the event loop can process cancellation.
            await asyncio.sleep(0.01)
            return None
        return self._messages.pop(0)


class _FakeClient:
    """Minimal redis.asyncio client stub."""

    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


class _FakeRedisService:
    """Stub for shared.services.redis.redis_service.RedisService."""

    def __init__(self, client: _FakeClient, snapshot: dict | None = None) -> None:
        self._client = client
        self._snapshot = snapshot

    async def _get_client(self):
        return self._client

    async def get(self, key: str):
        return self._snapshot


class _FakeConfig:
    """Captures update_rules calls."""

    def __init__(self) -> None:
        self.update_calls: list[tuple[dict, list]] = []

    def update_rules(
        self,
        tier_map: dict[str, TierLimits],
        system_rules: list[SystemRpmRule],
    ) -> None:
        self.update_calls.append((tier_map, system_rules))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_sets_running_and_creates_task():
    """start() must create a background asyncio task and mark the listener as running."""
    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=None)
    listener = RateLimitPubSubListener(redis_service)

    await listener.start()
    assert listener._is_running is True
    assert listener._task is not None
    assert not listener._task.done()

    await listener.stop()
    assert listener._is_running is False
    assert listener._task is None


@pytest.mark.asyncio
async def test_start_is_idempotent():
    """Calling start() twice must not create a second task."""
    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=None)
    listener = RateLimitPubSubListener(redis_service)

    await listener.start()
    first_task = listener._task

    await listener.start()
    assert listener._task is first_task

    await listener.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task_gracefully():
    """stop() must cancel the task and wait for it to finish."""
    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=None)
    listener = RateLimitPubSubListener(redis_service)

    await listener.start()
    task = listener._task

    await listener.stop()
    assert task.done()
    assert listener._task is None
    assert listener._is_running is False


@pytest.mark.asyncio
async def test_stop_unsubscribes_and_closes_pubsub():
    """stop() must unsubscribe from the channel and close the pubsub object."""
    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=None)
    listener = RateLimitPubSubListener(redis_service)

    await listener.start()
    # Give the loop time to subscribe and enter the poll cycle
    await asyncio.sleep(0.1)

    await listener.stop()
    assert RATE_LIMIT_UPDATES_CHANNEL in pubsub.subscribed_channels
    assert RATE_LIMIT_UPDATES_CHANNEL in pubsub.unsubscribed_channels
    assert pubsub._closed is True


@pytest.mark.asyncio
async def test_handle_update_refreshes_config_from_snapshot(monkeypatch):
    """When a Pub/Sub message arrives, the listener must fetch the snapshot
    from Redis and hot-swap the in-memory config."""
    fake_config = _FakeConfig()
    monkeypatch.setattr(
        "app.services.rate_limit.pubsub_listener.RateLimitConfig.get_instance",
        classmethod(lambda _cls: fake_config),
    )

    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=_SNAPSHOT)
    listener = RateLimitPubSubListener(redis_service)

    await listener._handle_update({"type": "message", "data": b'{"event":"rules_updated"}'})

    assert len(fake_config.update_calls) == 1
    tier_map, system_rules = fake_config.update_calls[0]
    assert "free" in tier_map
    assert "tier_1" in tier_map
    assert tier_map["free"] == TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    assert len(system_rules) == 2
    assert system_rules[0] == SystemRpmRule(
        method="POST", api_pattern="/v1/jobs", priority=100, rpm=30
    )


@pytest.mark.asyncio
async def test_refresh_from_snapshot_skips_when_no_snapshot(monkeypatch):
    """If no snapshot exists in Redis, refresh should log a warning and return."""
    fake_config = _FakeConfig()
    monkeypatch.setattr(
        "app.services.rate_limit.pubsub_listener.RateLimitConfig.get_instance",
        classmethod(lambda _cls: fake_config),
    )

    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=None)
    listener = RateLimitPubSubListener(redis_service)

    await listener._refresh_from_snapshot(source="test")
    assert fake_config.update_calls == []


@pytest.mark.asyncio
async def test_refresh_from_snapshot_handles_json_string(monkeypatch):
    """If the snapshot is returned as a raw JSON string (not pre-deserialized),
    the listener must parse it before applying."""
    fake_config = _FakeConfig()
    monkeypatch.setattr(
        "app.services.rate_limit.pubsub_listener.RateLimitConfig.get_instance",
        classmethod(lambda _cls: fake_config),
    )

    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(
        _FakeClient(pubsub), snapshot=json.dumps(_SNAPSHOT)
    )
    listener = RateLimitPubSubListener(redis_service)

    await listener._refresh_from_snapshot(source="test")

    assert len(fake_config.update_calls) == 1
    tier_map, _ = fake_config.update_calls[0]
    assert tier_map["tier_1"] == TierLimits(
        rpm_limit=15, max_concurrent_jobs=5, daily_quota=-1
    )


@pytest.mark.asyncio
async def test_refresh_from_snapshot_swallows_errors(monkeypatch):
    """If refreshing the snapshot raises, it must not crash the listener."""
    def _explode(*_args, **_kwargs):
        raise RuntimeError("config update boom")

    fake_config = _FakeConfig()
    fake_config.update_rules = _explode  # type: ignore[assignment]
    monkeypatch.setattr(
        "app.services.rate_limit.pubsub_listener.RateLimitConfig.get_instance",
        classmethod(lambda _cls: fake_config),
    )

    pubsub = _FakePubSub(messages=[])
    redis_service = _FakeRedisService(_FakeClient(pubsub), snapshot=_SNAPSHOT)
    listener = RateLimitPubSubListener(redis_service)

    # Should not raise
    await listener._refresh_from_snapshot(source="test")


@pytest.mark.asyncio
async def test_listen_loop_polls_on_timeout(monkeypatch):
    """When get_message returns None (timeout), the loop should call
    _refresh_from_snapshot with source='poll'."""
    refresh_sources: list[str] = []

    class _TrackingListener(RateLimitPubSubListener):
        async def _refresh_from_snapshot(self, source: str) -> None:
            refresh_sources.append(source)
            # Stop the loop after one poll to avoid hanging
            self._is_running = False

    pubsub = _FakePubSub(messages=[None])
    redis_service = _FakeRedisService(_FakeClient(pubsub))
    listener = _TrackingListener(redis_service)

    listener._is_running = True
    await listener._listen_loop()

    assert "poll" in refresh_sources


@pytest.mark.asyncio
async def test_listen_loop_handles_message(monkeypatch):
    """When get_message returns a message, the loop should call _handle_update."""
    handled_messages: list[dict] = []

    class _TrackingListener(RateLimitPubSubListener):
        async def _handle_update(self, message: dict) -> None:
            handled_messages.append(message)
            self._is_running = False

    message = {"type": "message", "data": b'{"event":"rules_updated"}'}
    pubsub = _FakePubSub(messages=[message])
    redis_service = _FakeRedisService(_FakeClient(pubsub))
    listener = _TrackingListener(redis_service)

    listener._is_running = True
    await listener._listen_loop()

    assert handled_messages == [message]
