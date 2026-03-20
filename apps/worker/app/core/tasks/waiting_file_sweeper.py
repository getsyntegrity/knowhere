"""
Waiting-File Sweeper — periodic Celery Beat task.

Scans for jobs stuck in 'waiting-file' status beyond UPLOAD_EXPIRE_SECONDS
and marks them as failed using ``SyncStateMachineService``.

CAS-protected transitions are safe to race against the S3 upload webhook.
"""
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select as sa_select

from shared.core.celery_app import get_celery_app
from shared.core.config import settings
from shared.core.database_sync import get_sync_db_context
from shared.core.state_machine.service_sync import SyncStateMachineService
from shared.core.state_machine.states import JobStatus
from shared.models.database.job import Job

celery_app = get_celery_app()

UPLOAD_EXPIRED_ERROR_MESSAGE = (
    "Upload expired: file was not uploaded within the allowed time window"
)
UPLOAD_EXPIRED_ERROR_CODE = "UPLOAD_EXPIRED"


@celery_app.task(name="app.core.tasks.waiting_file_sweeper.expire_stale_waiting_file_jobs")
def expire_stale_waiting_file_jobs() -> dict:
    """Expire jobs stuck in 'waiting-file' beyond ``UPLOAD_EXPIRE_SECONDS``.

    Runs every 30 minutes via Celery Beat.  Uses ``SyncStateMachineService``
    for CAS-protected state transitions and proper audit logging.
    """
    max_age: int = settings.UPLOAD_EXPIRE_SECONDS
    if max_age <= 0:
        return {"status": "skipped", "reason": "UPLOAD_EXPIRE_SECONDS <= 0"}

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age)
    expired_count = 0
    skipped_count = 0

    try:
        state_machine = SyncStateMachineService()

        with get_sync_db_context() as db:
            stmt = (
                sa_select(Job)
                .where(
                    Job.status == JobStatus.WAITING_FILE.value,
                    Job.created_at < cutoff,
                )
                .order_by(Job.created_at)
                .limit(200)
            )
            expired_jobs = db.execute(stmt).scalars().all()

            if not expired_jobs:
                logger.debug("Waiting-file sweeper: no expired jobs found")
                return {"status": "success", "expired": 0, "skipped": 0}

            for job in expired_jobs:
                success = state_machine.mark_failed(
                    db,
                    job.job_id,
                    error_message=UPLOAD_EXPIRED_ERROR_MESSAGE,
                    error_code=UPLOAD_EXPIRED_ERROR_CODE,
                    metadata={"sweeper": True},
                )
                if success:
                    expired_count += 1
                    logger.info(f"Expired waiting-file job {job.job_id}")
                else:
                    skipped_count += 1
                    logger.debug(f"Job {job.job_id} already transitioned (CAS miss)")

        if expired_count > 0:
            logger.info(
                f"Waiting-file sweeper completed: expired={expired_count}, "
                f"skipped={skipped_count}"
            )
        return {"status": "success", "expired": expired_count, "skipped": skipped_count}

    except Exception as e:
        logger.error(f"Waiting-file sweeper failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
