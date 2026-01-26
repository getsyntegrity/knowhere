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
from loguru import logger

# Explicitly import task modules to register tasks with Celery
# Note: Must import after celery_app to ensure decorators register correctly
import app.core.tasks.kb_tasks
import app.core.tasks.webhook_tasks  # Webhook dispatch task

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
    
    # Initialize logging configuration
    setup_logging()
    logger.info("Celery Worker logging configuration initialized")
    
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
    
    # Start worker with unique node name
    celery_app.worker_main([
        "worker", 
        f"--loglevel={log_level}", 
        "--concurrency=8",
        f"--hostname={node_name}"
    ])
