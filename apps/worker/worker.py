#!/usr/bin/env python3
"""
Celery Worker Startup Script
Starts the Celery worker with all registered tasks.
"""
import os
import sys
import asyncio

# Import from shared packages
from shared.core.celery_app import celery_app
from shared.core.config import redis_pool_manager
from shared.core.logging import setup_logging
from celery.signals import worker_init
from loguru import logger

# Explicitly import task modules to register tasks with Celery
# Note: Must import after celery_app to ensure decorators register correctly
import app.core.tasks.kb_tasks
import app.core.tasks.webhook_tasks


@worker_init.connect
def init_worker_logging(**kwargs):
    """Initialize structured logging and Logfire when worker process starts."""
    setup_logging(service_name="knowhere-worker")


async def init_redis():
    """Initialize Redis connection pool."""
    try:
        await redis_pool_manager.init_pool()
        logger.info("Celery Worker Redis connection pool initialized")
    except Exception as e:
        logger.error(f"Celery Worker Redis initialization failed: {e}")
        raise

if __name__ == "__main__":
    # Set environment variables
    os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")

    # Initialize Redis connection pool
    try:
        asyncio.run(init_redis())
    except Exception as e:
        logger.error(f"Worker startup failed: {e}")
        sys.exit(1)

    # Generate unique node name
    import socket
    hostname = socket.gethostname()
    pid = os.getpid()
    node_name = f"celery@{hostname}-{pid}"

    # Get log level setting
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()

    # Start worker with queue whitelist (CRITICAL: Exclude wait queues!)
    # If we don't specify -Q, specific workers will consume from ALL queues including wait queues,
    # which breaks the DLX retry delay (messages get consumed immediately instead of waiting).
    celery_app.worker_main([
        "worker",
        f"--loglevel={log_level}",
        "--concurrency=8",
        f"--hostname={node_name}",
        "-Q", "webhook_work,webhook_dead,kb_high,kb_medium,kb_low,ai_high_priority,default"
    ])
