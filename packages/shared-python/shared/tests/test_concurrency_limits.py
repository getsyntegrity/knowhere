import pytest

from shared.utils import concurrency_limits as mod
from shared.utils.concurrency_limits import (
    concurrency_limit,
    async_concurrency_limit,
)


@pytest.fixture(autouse=True)
def _reset_semaphores():
    """Clear cached semaphores between tests."""
    mod._sync_semaphores.clear()
    mod._async_semaphores.clear()
    yield
    mod._sync_semaphores.clear()
    mod._async_semaphores.clear()


# --- Sync tests ---


def test_concurrency_limit_acquires_and_releases():
    with concurrency_limit("rabbitmq_publish"):
        sem = mod._sync_semaphores["rabbitmq_publish"]
        # One slot consumed inside the context
        assert sem._value == 19  # 20 - 1

    # Slot released after exiting
    assert sem._value == 20


def test_concurrency_limit_uses_default_for_unknown_name():
    with concurrency_limit("unknown_service"):
        sem = mod._sync_semaphores["unknown_service"]
        assert sem._value == 9  # default limit=10, minus 1 acquired


def test_concurrency_limit_blocks_beyond_capacity():
    """Exhaust all slots, then verify the next acquire times out."""
    original_timeout = mod._ACQUIRE_TIMEOUT
    mod._ACQUIRE_TIMEOUT = 0.1  # speed up the test

    try:
        name = "mineru_upload"  # limit=10
        sem = mod._get_sync_semaphore(name)

        # Exhaust all 10 slots
        for _ in range(10):
            sem.acquire()

        with pytest.raises(TimeoutError, match="mineru_upload"):
            with concurrency_limit(name):
                pass  # should never reach here
    finally:
        mod._ACQUIRE_TIMEOUT = original_timeout


def test_concurrency_limit_releases_on_exception():
    """Slot is released even if the body raises."""
    name = "s3_upload"

    with pytest.raises(ValueError):
        with concurrency_limit(name):
            raise ValueError("boom")

    sem = mod._sync_semaphores[name]
    assert sem._value == 20  # fully released


def test_different_names_use_separate_semaphores():
    with concurrency_limit("llm_http"):
        with concurrency_limit("s3_upload"):
            llm_sem = mod._sync_semaphores["llm_http"]
            s3_sem = mod._sync_semaphores["s3_upload"]
            assert llm_sem._value == 29  # 30 - 1
            assert s3_sem._value == 19  # 20 - 1


# --- Async tests ---


@pytest.mark.asyncio
async def test_async_concurrency_limit_acquires_and_releases():
    async with async_concurrency_limit("llm_http"):
        sem = mod._async_semaphores["llm_http"]
        assert sem._value == 29  # 30 - 1

    assert sem._value == 30


@pytest.mark.asyncio
async def test_async_concurrency_limit_releases_on_exception():
    with pytest.raises(ValueError):
        async with async_concurrency_limit("s3_upload"):
            raise ValueError("boom")

    sem = mod._async_semaphores["s3_upload"]
    assert sem._value == 20


@pytest.mark.asyncio
async def test_async_concurrency_limit_timeout():
    original_timeout = mod._ACQUIRE_TIMEOUT
    mod._ACQUIRE_TIMEOUT = 0.1

    try:
        name = "mineru_upload"  # limit=10
        sem = mod._get_async_semaphore(name)

        # Exhaust all slots
        for _ in range(10):
            await sem.acquire()

        with pytest.raises(TimeoutError, match="mineru_upload"):
            async with async_concurrency_limit(name):
                pass
    finally:
        mod._ACQUIRE_TIMEOUT = original_timeout
