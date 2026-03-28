"""Tests for RedisJobLock distributed lock."""
from typing import Any, Optional, Sequence

import pytest

fakeredis = pytest.importorskip("fakeredis")

from shared.services.redis.distributed_lock import (
    RedisJobLock,
    _RENEW_SCRIPT,
)
from shared.core.exceptions.domain_exceptions import UnavailableException


# ---------------------------------------------------------------------------
# Fake SyncRedisService backed by fakeredis
# ---------------------------------------------------------------------------

class FakeSyncRedisService:
    """Minimal SyncRedisService stub that satisfies RedisJobLock's interface."""

    _KEY_PREFIX: str = "knowhere-api"

    def __init__(self, client=None):
        self._client = client or fakeredis.FakeRedis()

    def _get_client(self):
        return self._client

    def _build_key(self, key: str) -> str:
        prefix = self._KEY_PREFIX
        return f"{prefix}:{key}" if not key.startswith(prefix) else key

    def eval(self, script: str, keys: Sequence[str], args: Optional[Sequence[Any]] = None) -> Any:
        client = self._get_client()
        full_keys = [self._build_key(k) for k in keys]
        raw_args = list(args or [])
        return client.eval(script, len(full_keys), *(full_keys + raw_args))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_server():
    return fakeredis.FakeServer()


@pytest.fixture()
def redis_service(fake_server):
    client = fakeredis.FakeRedis(server=fake_server)
    return FakeSyncRedisService(client)


@pytest.fixture()
def redis_service_b(fake_server):
    """Second service sharing the same fake server (simulates another worker)."""
    client = fakeredis.FakeRedis(server=fake_server)
    return FakeSyncRedisService(client)


JOB_ID = "job_test_abc123"


# ---------------------------------------------------------------------------
# Acquire / Release basics
# ---------------------------------------------------------------------------

class TestAcquireRelease:
    def test_acquire_succeeds(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        assert lock.acquire() is True
        assert lock._acquired is True
        lock.release()

    def test_release_deletes_key(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        lock.acquire()
        full_key = redis_service._build_key(lock._lock_key)
        assert redis_service._get_client().exists(full_key) == 1
        lock.release()
        assert redis_service._get_client().exists(full_key) == 0

    def test_release_without_acquire_is_noop(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        assert lock.release() is False

    def test_double_release_is_safe(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        lock.acquire()
        assert lock.release() is True
        assert lock.release() is False


# ---------------------------------------------------------------------------
# Mutual exclusion
# ---------------------------------------------------------------------------

class TestMutualExclusion:
    def test_second_acquire_fails(self, redis_service, redis_service_b):
        lock_a = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        lock_b = RedisJobLock(redis_service_b, JOB_ID, ttl=5, renewal_interval=999)

        assert lock_a.acquire() is True
        assert lock_b.acquire() is False
        lock_a.release()

    def test_acquire_succeeds_after_release(self, redis_service, redis_service_b):
        lock_a = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        lock_b = RedisJobLock(redis_service_b, JOB_ID, ttl=5, renewal_interval=999)

        lock_a.acquire()
        lock_a.release()
        assert lock_b.acquire() is True
        lock_b.release()

    def test_different_jobs_dont_conflict(self, redis_service):
        lock_a = RedisJobLock(redis_service, "job_aaa", ttl=5, renewal_interval=999)
        lock_b = RedisJobLock(redis_service, "job_bbb", ttl=5, renewal_interval=999)

        assert lock_a.acquire() is True
        assert lock_b.acquire() is True
        lock_a.release()
        lock_b.release()


# ---------------------------------------------------------------------------
# Owner-only release (token safety)
# ---------------------------------------------------------------------------

class TestOwnerOnlyRelease:
    def test_cannot_release_someone_elses_lock(self, redis_service, redis_service_b):
        lock_a = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        lock_b = RedisJobLock(redis_service_b, JOB_ID, ttl=5, renewal_interval=999)

        lock_a.acquire()

        # Manually force lock_b to think it acquired (simulating a bug)
        lock_b._acquired = True
        lock_b._token = "wrong-token"
        assert lock_b.release() is False

        # lock_a's lock is still intact
        full_key = redis_service._build_key(lock_a._lock_key)
        assert redis_service._get_client().exists(full_key) == 1
        lock_a.release()

    def test_release_after_ttl_expiry_returns_false(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=1, renewal_interval=999)
        lock.acquire()
        lock._stop_renewal()

        # Simulate TTL expiry
        full_key = redis_service._build_key(lock._lock_key)
        redis_service._get_client().delete(full_key)

        assert lock.release() is False


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_acquires_and_releases(self, redis_service):
        full_key = redis_service._build_key(f"lock:job_processing:{JOB_ID}")

        with RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999):
            assert redis_service._get_client().exists(full_key) == 1

        assert redis_service._get_client().exists(full_key) == 0

    def test_context_manager_releases_on_exception(self, redis_service):
        full_key = redis_service._build_key(f"lock:job_processing:{JOB_ID}")

        with pytest.raises(ValueError, match="boom"):
            with RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999):
                raise ValueError("boom")

        assert redis_service._get_client().exists(full_key) == 0

    def test_context_manager_raises_unavailable_on_contention(
        self, redis_service, redis_service_b
    ):
        lock_a = RedisJobLock(redis_service, JOB_ID, ttl=5, renewal_interval=999)
        lock_a.acquire()

        with pytest.raises(UnavailableException):
            with RedisJobLock(redis_service_b, JOB_ID, ttl=5, renewal_interval=999):
                pass  # should never reach here

        lock_a.release()


# ---------------------------------------------------------------------------
# Renewal (Lua script correctness)
# ---------------------------------------------------------------------------

class TestRenewal:
    def test_renew_script_extends_ttl_for_owner(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=10, renewal_interval=999)
        lock.acquire()
        lock._stop_renewal()

        # Manually set a short TTL
        full_key = redis_service._build_key(lock._lock_key)
        redis_service._get_client().expire(full_key, 2)

        # Run the renew script
        result = redis_service.eval(
            _RENEW_SCRIPT,
            keys=[lock._lock_key],
            args=[lock._token, 60],
        )
        assert result == 1

        ttl = redis_service._get_client().ttl(full_key)
        assert ttl > 50  # should be close to 60
        lock.release()

    def test_renew_script_rejects_wrong_token(self, redis_service):
        lock = RedisJobLock(redis_service, JOB_ID, ttl=10, renewal_interval=999)
        lock.acquire()
        lock._stop_renewal()

        result = redis_service.eval(
            _RENEW_SCRIPT,
            keys=[lock._lock_key],
            args=["wrong-token", 60],
        )
        assert result == 0
        lock.release()

    def test_renew_script_returns_zero_for_missing_key(self, redis_service):
        result = redis_service.eval(
            _RENEW_SCRIPT,
            keys=["lock:job_processing:nonexistent"],
            args=["any-token", 60],
        )
        assert result == 0
