"""
Celery task definitions — base task class with lifecycle hooks.
"""

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app

celery_app = get_celery_app()


class BaseTask(Task):
    """Base task class with common lifecycle hooks."""

    def on_success(self, retval, task_id, args, kwargs):
        """Task success callback."""
        logger.info(f"Task {task_id} completed successfully")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Task failure callback."""
        logger.error(f"Task {task_id} failed: {exc}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Task retry callback."""
        logger.warning(f"Task {task_id} retrying: {exc}")
