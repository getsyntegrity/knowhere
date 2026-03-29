#!/usr/bin/env python3
# CRITICAL: Monkey patch MUST be the very first thing before ANY other imports.
# This patches stdlib (socket, ssl, threading, etc.) for cooperative greenlet scheduling.
import gevent.monkey
gevent.monkey.patch_all()

# Patch psycopg2 for cooperative DB access under gevent.
from psycogreen.gevent import patch_psycopg
patch_psycopg()

# Now safe to import everything else
import os
import socket
import sys

from app.core.runtime_limits import (
    apply_native_thread_caps,
)

apply_native_thread_caps()

from celery.signals import worker_init, worker_shutdown
from loguru import logger

from shared.core.celery_app import celery_app
from shared.core.logging import setup_logging
from shared.services.messaging.sync_publisher import close_sync_message_publisher
from shared.services.worker_health import (
    start_worker_heartbeat,
    stop_worker_heartbeat,
)

# Explicitly import task modules to register tasks with Celery
import app.core.tasks.kb_tasks
import app.core.tasks.stale_job_sweeper
import app.core.tasks.webhook_tasks


@worker_init.connect
def init_worker(**kwargs):
    """Initialize structured logging and sync Redis when worker process starts."""
    setup_logging(service_name="knowhere-worker")
    start_worker_heartbeat()

    # Patch gevent TaskPool to handle terminate_job gracefully.
    # Celery calls pool.terminate_job() when the AMQP connection drops
    # to cancel in-flight tasks, but gevent's pool raises NotImplementedError.
    # Since we use RedisJobLock to prevent duplicate execution on redelivery,
    # we can safely make this a no-op warning instead of a crash.
    try:
        from celery.concurrency.gevent import TaskPool as GeventTaskPool
        if not hasattr(GeventTaskPool, '_original_terminate_job'):
            def _graceful_terminate_job(self, pid, signal=None):
                logger.warning(
                    f"gevent pool cannot kill greenlet (pid={pid}), "
                    f"relying on RedisJobLock for dedup on redelivery"
                )
            GeventTaskPool._original_terminate_job = getattr(GeventTaskPool, 'terminate_job', None)
            GeventTaskPool.terminate_job = _graceful_terminate_job
            logger.info("Patched gevent TaskPool.terminate_job for graceful AMQP recovery")
    except Exception as e:
        logger.warning(f"Could not patch gevent TaskPool: {e}")

    # Verify Redis connectivity (lazy init on first use if this fails)
    try:
        from shared.services.redis.redis_sync_service import SyncRedisServiceFactory
        service = SyncRedisServiceFactory.get_service()
        if service.ping():
            logger.info("Worker sync Redis connection verified")
        else:
            logger.warning("Worker sync Redis ping failed, will retry on first use")
    except Exception as e:
        logger.warning(f"Worker sync Redis init deferred: {e}")


@worker_shutdown.connect
def shutdown_worker(**kwargs):
    """Clean up shared resources on worker shutdown."""
    try:
        close_sync_message_publisher()
        logger.info("Worker sync message publisher closed")
    except Exception as e:
        logger.warning(f"Worker sync message publisher cleanup failed: {e}")

    try:
        stop_worker_heartbeat()
        logger.info("Worker heartbeat stopped")
    except Exception as e:
        logger.warning(f"Worker heartbeat cleanup failed: {e}")

    try:
        from shared.utils.http_clients import close_sync_client
        close_sync_client()
        logger.info("Worker sync HTTP client closed")
    except Exception as e:
        logger.warning(f"Worker HTTP client cleanup failed: {e}")


if __name__ == "__main__":
    # Generate unique node name
    hostname = socket.gethostname()
    pid = os.getpid()
    node_name = f"celery@{hostname}-{pid}"

    # Get log level setting
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()

    # Start worker with gevent pool
    # Queue whitelist: exclude wait queues to preserve DLX retry delays
    from shared.core.config import settings
    concurrency = settings.WORKER_CONCURRENCY

    celery_args = [
        "worker",
        "--pool=gevent",
        f"--concurrency={concurrency}",
        f"--loglevel={log_level}",
        f"--hostname={node_name}",
        "-Q", "webhook_work,webhook_dead,kb_high,kb_medium,kb_low,ai_high_priority,default",
        "--without-gossip",
        "--without-mingle",
    ]

    import subprocess
    logger.info("Starting standalone Celery Beat process using RedBeat locking")
    subprocess.Popen([
        sys.executable, "-m", "celery", "-A", "shared.core.celery_app", "beat", f"--loglevel={log_level}"
    ])

    celery_app.worker_main(celery_args)
