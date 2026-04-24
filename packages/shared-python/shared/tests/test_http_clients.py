import pytest

from shared.utils import http_clients as mod
from shared.utils.http_clients import (
    close_async_client,
    close_sync_client,
    get_async_client,
    get_sync_client,
)


@pytest.fixture(autouse=True)
def _reset_clients():
    """Ensure clean state between tests."""
    mod._sync_client = None
    mod._async_client = None
    yield
    # Cleanup any clients created during the test
    if mod._sync_client is not None:
        mod._sync_client.close()
        mod._sync_client = None
    if mod._async_client is not None:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pass  # will be cleaned up by gc
            else:
                loop.run_until_complete(mod._async_client.aclose())
        except Exception:
            pass
        mod._async_client = None


# --- Sync client tests ---


def test_get_sync_client_returns_httpx_client():
    import httpx

    client = get_sync_client()
    assert isinstance(client, httpx.Client)


def test_get_sync_client_returns_same_instance():
    client1 = get_sync_client()
    client2 = get_sync_client()
    assert client1 is client2


def test_get_sync_client_has_correct_timeout():
    client = get_sync_client()
    assert client.timeout.connect == 10.0
    assert client.timeout.read == 300.0
    assert client.timeout.write == 60.0
    assert client.timeout.pool == 30.0


def test_get_sync_client_follows_redirects():
    client = get_sync_client()
    assert client.follow_redirects is True


def test_close_sync_client_clears_singleton():
    get_sync_client()
    assert mod._sync_client is not None

    close_sync_client()
    assert mod._sync_client is None


def test_close_sync_client_allows_new_instance():
    client1 = get_sync_client()
    close_sync_client()
    client2 = get_sync_client()
    assert client1 is not client2


def test_close_sync_client_noop_when_none():
    """Closing when no client exists should not raise."""
    close_sync_client()  # should not raise


# --- Async client tests ---


def test_get_async_client_returns_httpx_async_client():
    import httpx

    client = get_async_client()
    assert isinstance(client, httpx.AsyncClient)


def test_get_async_client_returns_same_instance():
    client1 = get_async_client()
    client2 = get_async_client()
    assert client1 is client2


def test_get_async_client_follows_redirects():
    client = get_async_client()
    assert client.follow_redirects is True


@pytest.mark.asyncio
async def test_close_async_client_clears_singleton():
    get_async_client()
    assert mod._async_client is not None

    await close_async_client()
    assert mod._async_client is None


@pytest.mark.asyncio
async def test_close_async_client_allows_new_instance():
    client1 = get_async_client()
    await close_async_client()
    client2 = get_async_client()
    assert client1 is not client2


@pytest.mark.asyncio
async def test_close_async_client_noop_when_none():
    """Closing when no client exists should not raise."""
    await close_async_client()  # should not raise
