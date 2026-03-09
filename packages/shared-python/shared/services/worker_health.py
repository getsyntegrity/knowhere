"""
Local-only worker heartbeat used by container health probes.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import gevent
from gevent.event import Event
from gevent.lock import Semaphore
from loguru import logger


HEARTBEAT_PATH = Path(
    os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/knowhere-worker-heartbeat.json")
)
HEARTBEAT_INTERVAL_SECONDS = float(
    os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "5")
)
HEARTBEAT_STALE_AFTER_SECONDS = float(
    os.getenv("WORKER_HEARTBEAT_STALE_AFTER_SECONDS", "45")
)

_heartbeat_greenlet: Optional[gevent.Greenlet] = None
_heartbeat_stop_event = Event()
_heartbeat_lock = Semaphore()


def write_worker_heartbeat() -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = HEARTBEAT_PATH.with_suffix(f"{HEARTBEAT_PATH.suffix}.tmp")
    temp_path.write_text(str(os.getpid()), encoding="utf-8")
    os.replace(temp_path, HEARTBEAT_PATH)


def _heartbeat_loop() -> None:
    while not _heartbeat_stop_event.is_set():
        try:
            write_worker_heartbeat()
        except Exception as exc:
            logger.warning(f"Failed to write worker heartbeat: {exc}")
        gevent.sleep(HEARTBEAT_INTERVAL_SECONDS)


def start_worker_heartbeat() -> None:
    global _heartbeat_greenlet

    with _heartbeat_lock:
        if _heartbeat_greenlet is not None and not _heartbeat_greenlet.dead:
            return
        _heartbeat_stop_event.clear()
        write_worker_heartbeat()
        _heartbeat_greenlet = gevent.spawn(_heartbeat_loop)
        logger.info(
            "Worker heartbeat started: "
            f"path={HEARTBEAT_PATH}, interval={HEARTBEAT_INTERVAL_SECONDS}s"
        )


def stop_worker_heartbeat() -> None:
    global _heartbeat_greenlet

    with _heartbeat_lock:
        _heartbeat_stop_event.set()
        heartbeat_greenlet = _heartbeat_greenlet
        _heartbeat_greenlet = None

    if heartbeat_greenlet is not None and not heartbeat_greenlet.dead:
        heartbeat_greenlet.kill(block=True, timeout=1)

    try:
        HEARTBEAT_PATH.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning(f"Failed to remove worker heartbeat file: {exc}")


def assert_worker_healthy() -> None:
    if not HEARTBEAT_PATH.exists():
        raise SystemExit(f"Worker heartbeat file not found: {HEARTBEAT_PATH}")

    age_seconds = time.time() - HEARTBEAT_PATH.stat().st_mtime
    if age_seconds > HEARTBEAT_STALE_AFTER_SECONDS:
        raise SystemExit(
            "Worker heartbeat stale: "
            f"path={HEARTBEAT_PATH}, age={age_seconds:.1f}s, "
            f"threshold={HEARTBEAT_STALE_AFTER_SECONDS:.1f}s"
        )
