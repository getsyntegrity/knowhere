"""
Knowledge-base workflow orchestration.
"""

from typing import Optional

from loguru import logger

from shared.core.celery_router import task_router

# Tasks now run in the Worker service and are referenced by task name.
from shared.core.exceptions.domain_exceptions import (
    KnowhereException,
    WorkerHandlingException,
)


class KBOrchestrator:
    """Coordinate knowledge-base processing jobs."""

    def __init__(self):
        self.task_router = task_router

    async def start_workflow(
        self,
        db,
        job_id: str,
        source_type: str,
        file_path: Optional[str] = None,
        file_url: Optional[str] = None,
        user_id: str = None,
    ) -> str:
        """
        Start the knowledge-base workflow.

        Args:
            db: Database session.
            job_id: Job identifier.
            source_type: Source type.
            file_path: Uploaded file path when direct upload is used.
            file_url: Source URL when URL ingestion is used.
            user_id: User identifier.

        Returns:
            str: Celery task identifier.
        """
        try:
            # When the source is a URL, recover file_url from job metadata if needed.
            if source_type == "url" and not file_url:
                from app.repositories.job_repository import JobRepository

                from shared.models.schemas.job_metadata import JobMetadataHelper
                from shared.services.redis import RedisServiceFactory

                job_repo = JobRepository()
                redis_service = RedisServiceFactory.get_service()
                job_metadata = await job_repo.get_job_metadata(
                    db, job_id, redis_service
                )
                file_url = JobMetadataHelper.get_field(job_metadata, "file_url")

            # Resolve the queue name for this job.
            queue_name = self.task_router.get_queue_for_job("kb_management", user_id)
            task_kwargs = {
                "user_id": user_id,
                "job_type": "kb_management",
            }

            # Start the single worker task. Upload is already complete via S3.
            # The task handles parsing, vectorization, ZIP generation, S3 upload,
            # and result publication. Webhook and email delivery stay in the API.
            from celery import signature

            task_signature = signature(
                "app.core.tasks.kb_tasks.parse_task",
                args=[job_id],
                kwargs=task_kwargs,
            ).set(queue=queue_name)

            # Enqueue the task.
            result = task_signature.apply_async()

            logger.info(
                f"Knowledge-base workflow started: job_id={job_id}, task_id={result.id}, queue={queue_name}"
            )

            return result.id

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to start knowledge-base workflow: {e}")
            raise WorkerHandlingException(
                internal_message=f"Failed to start knowledge-base workflow: {str(e)}",
                original_exception=e,
            )

    def create_workflow_chain(self, job_id: str, user_id: str, queue_name: str = None):
        """
        Create the workflow signature for tests or manual execution.

        Args:
            job_id: Job identifier.
            user_id: User identifier.
            queue_name: Optional explicit queue name.

        Returns:
            signature: Celery task signature.
        """
        if not queue_name:
            queue_name = self.task_router.get_queue_for_job("kb_management", user_id)
        task_kwargs = {
            "user_id": user_id,
            "job_type": "kb_management",
        }

        from celery import signature

        # Return the single-task signature. Parsing, vectorization, ZIP generation,
        # S3 upload, and publication happen in the worker. Webhook and email
        # delivery remain in the API service.
        return signature(
            "app.core.tasks.kb_tasks.parse_task",
            args=[job_id],
            kwargs=task_kwargs,
        ).set(queue=queue_name)

    def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel a workflow.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            bool: Whether cancellation succeeded.
        """
        try:
            from shared.core.celery_app import get_celery_app

            celery_app = get_celery_app()

            result = celery_app.AsyncResult(workflow_id)
            result.revoke(terminate=True)

            logger.info(f"Workflow cancelled: {workflow_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel workflow: {e}")
            return False
