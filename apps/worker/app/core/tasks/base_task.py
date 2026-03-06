"""
Base Celery task class for KB worker tasks.
Provides centralized exception handling, failure/retry messaging.
"""
from typing import Optional

from celery import Task
from loguru import logger

from shared.core.state_machine.states import JobStatus
from shared.core.logging import LogEvent
from shared.core.exceptions.domain_exceptions import UnknownException
from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.services.messaging.sync_publisher import get_sync_message_publisher


class KBBaseTask(Task):
    """Knowledge Base base task class - provides centralized exception handling."""

    def on_success(self, retval, task_id, args, kwargs):
        """Task success callback."""
        logger.bind(
            event=LogEvent.WORKER_TASK_COMPLETE.value,
            task_id=task_id,
        ).info("KB task completed successfully")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Task failure callback - Centralized exception handling."""
        job_id = self._extract_job_id(args, kwargs)

        # Normalize to KnowhereException
        knowhere_exc = exc if isinstance(exc, KnowhereException) else UnknownException(original_exception=exc)

        # Use exc.logging() for canonical exception logging
        knowhere_exc.logging(job_id=job_id)

        # Get error info from to_client
        client_response = knowhere_exc.to_client(job_id or "Null")
        error_info = client_response["error"]

        # Publish failure message using sync publisher
        if job_id:
            try:
                message_publisher = get_sync_message_publisher()

                # Include stack trace only for wrapped exceptions
                stack_trace = str(einfo) if knowhere_exc.original_exception else None

                message_publisher.publish_failure(
                    job_id=job_id,
                    error_message=error_info["message"],
                    error_code=error_info["code"],
                    error_type=type(exc).__name__,
                    stack_trace=stack_trace,
                    metadata={
                        "refund_credits": True,
                        "details": error_info.get("details"),
                        "task_id": task_id,
                    },
                )
                logger.info(f"Failure message published: job_id={job_id}, error_code={error_info['code']}")
            except Exception as e:
                logger.error(f"Failed to publish failure message: job_id={job_id}, error={e}")

    def _extract_job_id(self, args, kwargs) -> Optional[str]:
        """Extract job_id from args or kwargs."""
        if args and len(args) > 0:
            if isinstance(args[0], dict) and "job_id" in args[0]:
                return args[0]["job_id"]
            elif isinstance(args[0], str):
                return args[0]
        if "job_id" in kwargs:
            return kwargs["job_id"]
        return None

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Task retry callback - publishes retry status to API service."""
        job_id = self._extract_job_id(args, kwargs)

        logger.bind(
            event=LogEvent.WORKER_TASK_RETRY.value,
            task_id=task_id,
            job_id=job_id,
            retry_count=self.request.retries,
        ).warning(f"KB task retrying: {exc}")

        if job_id:
            try:
                message_publisher = get_sync_message_publisher()
                message_publisher.publish_status_update(
                    job_id=job_id,
                    status=JobStatus.RUNNING.value,
                    trigger="task_retry",
                    metadata={
                        "retry_count": self.request.retries,
                        "error_message": str(exc),
                        "task_id": task_id,
                    },
                    operator_type="system",
                )
                logger.info(f"Retry message published: job_id={job_id}, retry_count={self.request.retries}")
            except Exception as e:
                logger.error(f"Failed to publish retry message: {e}")
