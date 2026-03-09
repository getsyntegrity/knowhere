"""
Per-provider concurrency caps using named semaphores.
Prevents all 150 greenlets from hitting the same external
service simultaneously during network instability.
"""
import asyncio
import threading
from contextlib import contextmanager, asynccontextmanager
from typing import Dict

from loguru import logger

from shared.core.logging import LogEvent

# Default concurrency limits per provider
_DEFAULT_LIMITS: Dict[str, int] = {
    "rabbitmq_publish": 20,
    "llm_http": 30,
    "mineru_upload": 10,
    "s3_upload": 20,
    "file_download": 20,
}

_ACQUIRE_TIMEOUT = 60.0  # seconds

# --- Sync semaphores (gevent-patched threading.Semaphore) ---
_sync_semaphores: Dict[str, threading.Semaphore] = {}
_sync_lock = threading.Lock()


def _get_sync_semaphore(name: str) -> threading.Semaphore:
    if name not in _sync_semaphores:
        with _sync_lock:
            if name not in _sync_semaphores:
                limit = _DEFAULT_LIMITS.get(name, 10)
                _sync_semaphores[name] = threading.Semaphore(limit)
    return _sync_semaphores[name]


@contextmanager
def concurrency_limit(name: str):
    """Sync context manager that caps concurrency for a named resource."""
    sem = _get_sync_semaphore(name)
    acquired = sem.acquire(timeout=_ACQUIRE_TIMEOUT)
    if not acquired:
        logger.bind(event=LogEvent.CONCURRENCY_LIMIT_TIMEOUT.value).error(
            f"Concurrency limit timeout: name={name}, "
            f"timeout={_ACQUIRE_TIMEOUT}s"
        )
        raise TimeoutError(
            f"Could not acquire concurrency slot '{name}' "
            f"within {_ACQUIRE_TIMEOUT}s"
        )
    try:
        yield
    finally:
        sem.release()


# --- Async semaphores ---
_async_semaphores: Dict[str, asyncio.Semaphore] = {}
_async_lock = threading.Lock()


def _get_async_semaphore(name: str) -> asyncio.Semaphore:
    if name not in _async_semaphores:
        with _async_lock:
            if name not in _async_semaphores:
                limit = _DEFAULT_LIMITS.get(name, 10)
                _async_semaphores[name] = asyncio.Semaphore(limit)
    return _async_semaphores[name]


@asynccontextmanager
async def async_concurrency_limit(name: str):
    """Async context manager that caps concurrency for a named resource."""
    sem = _get_async_semaphore(name)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=_ACQUIRE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.bind(event=LogEvent.CONCURRENCY_LIMIT_TIMEOUT.value).error(
            f"Async concurrency limit timeout: name={name}, "
            f"timeout={_ACQUIRE_TIMEOUT}s"
        )
        raise TimeoutError(
            f"Could not acquire async concurrency slot '{name}' "
            f"within {_ACQUIRE_TIMEOUT}s"
        )
    try:
        yield
    finally:
        sem.release()
