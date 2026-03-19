"""
Knowledge Base Management Celery Tasks

Sync implementation for gevent worker pool.
All I/O operations use sync services that yield cooperatively under gevent.
"""
import os
import tempfile

import requests
from loguru import logger
from sqlalchemy import select

from shared.core.celery_app import get_celery_app
from shared.core.state_machine.states import JobStatus
from shared.core.config import settings
from shared.core.logging import log_context, LogEvent

# Sync services for gevent worker
from shared.core.database_sync import get_sync_db_context
from shared.services.redis.redis_sync_service import (
    SyncRedisServiceFactory,
    SyncJobInfoRedisService,
    SyncJobMetadataService,
    SyncChunksRedisService,
)
from shared.services.messaging.sync_publisher import get_sync_message_publisher

# Exception handling
from shared.core.exceptions.domain_exceptions import (
    ValidationException,
    FileSystemException,
    NotFoundException,
    StorageServiceException,
    WorkerHandlingException,
    SystemSettingMissingException,
    SystemSettingInvalidException,
    InsufficientCreditsException,
)
from shared.core.exceptions import RETRYABLE_EXCEPTIONS

# Storage operations
from app.services.storage.sync_storage_service import (
    verify_s3_file_exists,
    generate_download_url,
    upload_to_s3,
    upload_zip_result,
    download_file_from_url,
)

# Base task class
from app.core.tasks.base_task import KBBaseTask

# Domain services
from shared.core.billing import BillingCalculator
from shared.models.database.job import Job
from shared.models.schemas.job_metadata import JobMetadataHelper
from shared.services.storage.zip_result_service import ZipResultService
from app.services.workload.page_estimator import PageEstimator

# Get Celery application
celery_app = get_celery_app()


def _cleanup_temp_file(file_path: str | None) -> None:
    """Best-effort cleanup for temp files created during parsing."""
    if not file_path:
        return

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as exc:
        logger.warning(f"Failed to cleanup temp file {file_path}: {exc}")


def _download_s3_file_to_temp(file_url: str, file_ext: str) -> str:
    """Download the source file from object storage into a temp file."""
    local_temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            local_temp_path = tmp_file.name
            with requests.get(
                file_url,
                timeout=120,
                stream=True,
                headers={"User-Agent": "Knowhere-Worker/1.0"},
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        tmp_file.write(chunk)
    except requests.RequestException as exc:
        _cleanup_temp_file(local_temp_path)
        raise StorageServiceException(
            internal_message=f"Failed to download source file from object storage: {exc}",
            operation="download_source_file",
            original_exception=exc,
        ) from exc

    return local_temp_path


@celery_app.task(
    bind=True,
    base=KBBaseTask,
    name="app.core.tasks.kb_tasks.upload_url_file_task",
    ignore_result=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={"countdown": settings.KB_TASK_RETRY_COUNTDOWN, "max_retries": settings.KB_TASK_MAX_RETRIES},
)
def upload_url_file_task(self, job_id: str, source_url: str, user_id: str | None = None, job_type: str | None = None):
    """Download file from URL and upload to S3."""
    with log_context(task_id=self.request.id):
        logger.bind(event=LogEvent.WORKER_TASK_START.value).info("Task started: upload_url_file_task")

        if not job_id:
            raise WorkerHandlingException(
                user_message="An unexpected system error occurred",
                internal_message="Worker task 'upload_url_file_task' called without job_id",
            )

        result = _upload_url_file(job_id, source_url, user_id, job_type)

        logger.bind(event=LogEvent.WORKER_TASK_COMPLETE.value).info("Task completed: upload_url_file_task")
        return result


def _upload_url_file(job_id: str, source_url: str, user_id: str | None, job_type: str | None = None):
    """Sync URL file download and upload to S3."""
    message_publisher = get_sync_message_publisher()

    # Get job info from Redis
    redis_service = SyncRedisServiceFactory.get_service()
    job_info_service = SyncJobInfoRedisService(redis_service)
    job_info = job_info_service.get_job_info(job_id)

    if not job_info:
        metadata_service = SyncJobMetadataService(redis_service)
        job_metadata = metadata_service.get_metadata(job_id)
        if job_metadata:
            s3_key = job_metadata.get("s3_key")
        else:
            raise NotFoundException(
                resource="JobInfo",
                resource_id=job_id,
                internal_message="Job info not found in Redis or Metadata",
            )
    else:
        s3_key = job_info.get("s3_key")

    if not s3_key:
        raise NotFoundException(
            resource="JobInfo",
            resource_id="s3_key",
            internal_message=f"Missing s3_key in Redis job info for job_id={job_id}",
        )

    # Publish progress: validating file type
    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=3,
        message_text="Validating URL file type...",
    )

    # Step 1: Validate URL file type (path first, then Content-Type header)
    from shared.utils.url_file_type import resolve_file_extension_sync

    file_extension = resolve_file_extension_sync(source_url)

    if not file_extension:
        all_supported_extensions = settings.get_supported_extensions()
        supported_formats = ", ".join(sorted(all_supported_extensions))
        raise ValidationException(
            user_message="Unsupported file type",
            violations=[{"field": "file_extension", "description": f"Must be one of: {supported_formats}"}],
        )

    # Publish progress: downloading
    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=10,
        message_text="Downloading file from URL...",
    )

    # Step 2: Download file to temp directory
    try:
        temp_file_path = download_file_from_url(source_url)
    except Exception as e:
        raise ValidationException(
            user_message="Failed to download file from URL",
            violations=[{"field": "source_url", "description": "Could not download file from the provided URL"}],
            internal_message=f"Failed to download file from URL: {source_url}, error: {e}",
        )

    try:
        # Publish progress: validating file size
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=30,
            message_text="Validating file size...",
        )

        # Step 3: Validate file size
        file_size = os.path.getsize(temp_file_path)

        if file_size > settings.MAX_FILE_SIZE:
            limit_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
            raise ValidationException(
                user_message=f"File size exceeds limit (max {limit_mb}MB for {file_extension})",
                violations=[{"field": "file_size", "description": f"Size {file_size} bytes exceeds limit of {settings.MAX_FILE_SIZE} bytes"}],
            )

        # Publish progress: uploading to S3
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=50,
            message_text="Uploading file to S3...",
        )

        # Step 4: Upload to S3
        uploads_bucket = settings.S3_BUCKET_NAME
        upload_to_s3(temp_file_path, s3_key, uploads_bucket)
        logger.info(f"File uploaded to S3: {s3_key}")

    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.debug(f"Temp file cleaned up: {temp_file_path}")

    # Publish progress: verifying upload
    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=80,
        message_text="Verifying upload result...",
    )

    # Step 5: Verify S3 file exists
    file_info = verify_s3_file_exists(s3_key)
    if not file_info.get("exists"):
        raise StorageServiceException(
            user_message="We failed to verify your file upload",
            internal_message=f"S3 file verification failed for {s3_key}",
        )

    # Publish progress: complete
    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=100,
        message_text="URL file upload complete, waiting for processing...",
    )

    logger.info(f"URL file upload complete, waiting for S3 webhook: {job_id} -> {s3_key}")

    return {
        "status": "success",
        "job_id": job_id,
        "s3_key": s3_key,
        "file_size": file_info.get("size"),
    }


@celery_app.task(
    bind=True,
    base=KBBaseTask,
    name="app.core.tasks.kb_tasks.parse_task",
    ignore_result=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={"countdown": settings.KB_TASK_RETRY_COUNTDOWN, "max_retries": settings.KB_TASK_MAX_RETRIES},
)
def parse_task(self, job_id: str, user_id: str | None = None, job_type: str = "kb_management"):
    """Parse and vectorize task (file already uploaded to S3)."""
    with log_context(task_id=self.request.id):
        logger.bind(event=LogEvent.WORKER_TASK_START.value).info("Task started: parse_task")

        if not job_id:
            raise WorkerHandlingException(
                user_message="An unexpected system error occurred",
                internal_message="Worker task 'parse_task' called without job_id",
            )

        result = _parse(job_id, user_id)

        logger.bind(event=LogEvent.WORKER_TASK_COMPLETE.value).info("Task completed: parse_task")
        return result


def _parse(job_id: str, user_id: str | None):
    """Sync parse and vectorize (file already uploaded to S3)."""
    logger.info(f"Parse started: job_id={job_id}, user_id={user_id}")
    message_publisher = get_sync_message_publisher()

    # Get job info from Redis (sync)
    redis_service = SyncRedisServiceFactory.get_service()
    job_info_service = SyncJobInfoRedisService(redis_service)
    job_info = job_info_service.get_job_info(job_id)

    if not job_info:
        raise NotFoundException(
            resource="JobInfo",
            resource_id=job_id,
            internal_message="job info not found in Redis",
        )

    s3_key = job_info.get("s3_key")
    if not s3_key:
        raise NotFoundException(
            resource="JobInfo",
            resource_id="s3_key",
            internal_message="Missing s3_key in job_info",
        )

    job_user_id = job_info.get("user_id") or user_id

    # Verify S3 file exists (sync)
    file_info = verify_s3_file_exists(s3_key)
    if not file_info.get("exists"):
        raise NotFoundException(
            resource="S3File",
            resource_id=s3_key,
            internal_message=f"S3 file not found: {s3_key}",
        )

    logger.info(f"S3 file verified: {s3_key}")

    # Validate file size
    file_size = file_info.get("size", 0)
    file_extension = os.path.splitext(s3_key)[1].lower()

    if file_size > settings.MAX_FILE_SIZE:
        limit_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
        raise ValidationException(
            user_message=f"File size exceeds limit (max {limit_mb}MB for {file_extension})",
            violations=[{"field": "file_size", "description": f"Size {file_size} bytes exceeds limit of {settings.MAX_FILE_SIZE} bytes"}],
        )

    # Get job_metadata from Redis
    metadata_service = SyncJobMetadataService(redis_service)
    job_metadata = metadata_service.get_metadata(job_id)
    if not job_metadata:
        raise NotFoundException(
            resource="JobMetadata",
            resource_id=job_id,
            internal_message=f"Job metadata not found for job_id={job_id}",
        )

    # Validate output directory
    parent_path = settings.USERS_DATA_PATH
    if not parent_path:
        raise SystemSettingMissingException(
            user_message="System configuration error",
            internal_message="USERS_DATA_PATH not configured",
        )

    if not os.path.isabs(parent_path):
        raise SystemSettingInvalidException(
            user_message="System configuration error",
            internal_message=f"USERS_DATA_PATH must be absolute path, current value: {parent_path}",
        )

    output_dir = os.path.join(parent_path, f"kb_{job_user_id}", job_id)

    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Output directory ready: {output_dir}")
    except (OSError, PermissionError) as e:
        raise FileSystemException(
            user_message="System error preparing storage",
            operation="create_directory",
            internal_message=f"Failed to create directory: {output_dir}",
            original_exception=e,
        )

    # Publish status: start processing
    message_publisher.publish_status_update(
        job_id=job_id,
        status=JobStatus.RUNNING.value,
        trigger="start_processing",
        previous_status=None,
        operator_type="system",
    )

    # Publish progress: start parsing
    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=10,
        message_text="Parsing document...",
    )

    # Generate download URL and download file (sync)
    file_url_response = generate_download_url(s3_key, settings.S3_BUCKET_NAME)
    file_url = file_url_response["download_url"]

    filename = JobMetadataHelper.get_field(job_metadata, "source_file_name")

    # Download file to temp location
    page_count = 1

    # Derive file extension from s3_key (always has the correct extension)
    # rather than filename, which may not have a real extension for URLs
    # like arxiv.org/pdf/1706.03762
    file_ext = os.path.splitext(s3_key)[1].lower() if s3_key else ""
    local_temp_path = _download_s3_file_to_temp(file_url, file_ext)

    logger.info(f"File downloaded: job_id={job_id}, local_path={local_temp_path}")

    # Estimate workload
    page_count = PageEstimator.estimate(local_temp_path)
    logger.info(f"Workload estimation: job_id={job_id}, page_count={page_count}")

    # Synchronous billing - deduct credits before processing
    with get_sync_db_context() as db:
        job_result = db.execute(
            select(Job).where(Job.job_id == job_id).with_for_update()
        )
        job = job_result.scalar_one_or_none()

        if job and getattr(job, "billing_status", "") == "charged":
            logger.info(f"Job already charged: {job_id}")
        else:
            billing_calc = BillingCalculator()
            micro_dollar_required = billing_calc.calculate_page_cost(page_count)

            try:
                # Inline sync billing using the ledger pattern:
                # 1. Check balance, 2. Insert transaction, 3. Recalculate, 4. Update balance
                from sqlalchemy import func as sa_func
                from shared.models.database.credits_transaction import CreditsTransaction
                from shared.models.database.user_balance import UserBalance

                # Check current balance
                balance_result = db.execute(
                    select(UserBalance.credits_balance).where(UserBalance.user_id == job_user_id)
                )
                current_balance = balance_result.scalar() or 0

                if current_balance < micro_dollar_required.amount:
                    raise InsufficientCreditsException(
                        user_message=f"Insufficient credits. Required: {micro_dollar_required.amount}, Available: {current_balance}",
                        required_credits=micro_dollar_required.amount,
                        internal_message=f"User {job_user_id} has insufficient credits",
                    )

                # Insert transaction record (ledger entry)
                transaction = CreditsTransaction(
                    user_id=job_user_id,
                    credits_amount=-micro_dollar_required.amount,
                    transaction_type="usage",
                    description=billing_calc.format_description(page_count, filename),
                )
                db.add(transaction)
                db.flush()

                # Recalculate balance from ledger
                agg_result = db.execute(
                    select(sa_func.coalesce(sa_func.sum(CreditsTransaction.credits_amount), 0))
                    .where(CreditsTransaction.user_id == job_user_id)
                )
                new_balance = int(agg_result.scalar() or 0)

                # Update materialized view
                from sqlalchemy import update as sa_update
                db.execute(
                    sa_update(UserBalance)
                    .where(UserBalance.user_id == job_user_id)
                    .values(credits_balance=new_balance)
                )

                if job:
                    job.page_count = page_count
                    job.credits_charged = micro_dollar_required.amount
                    job.billing_status = "charged"

                db.commit()
                logger.bind(
                    operation_cost=micro_dollar_required.amount,
                    operation_cost_unit="micro_dollar",
                    credits_charged=micro_dollar_required.to_credit(),
                    new_balance=new_balance,
                    user_id=job_user_id,
                ).info("Billing successful")

            except InsufficientCreditsException as e:
                logger.error(f"Billing failed: job_id={job_id}, user_id={job_user_id}")
                if local_temp_path and os.path.exists(local_temp_path):
                    os.unlink(local_temp_path)

                if job:
                    job.billing_status = "billing_failed"
                    db.commit()

                raise InsufficientCreditsException(
                    user_message=f"Insufficient credits to process this document ({page_count} pages required, cost: {micro_dollar_required.to_credit()}).",
                    required_credits=micro_dollar_required.to_credit(),
                    internal_message=f"job_id={job_id}, user_id={job_user_id}, page_count={page_count}",
                )

    # Store billing info in Redis
    metadata_service.update_metadata(job_id, {
        "page_count": page_count,
        "billing_status": "charged",
    })

    # Call parsing service
    from app.services.document_parser.parse_service import checkerboard_inject_parse

    doc_type = JobMetadataHelper.get_parsing_param(job_metadata, "doc_type", "auto")
    logger.info(f"Start parse: job_id={job_id}, filename={filename}, type={doc_type}")

    try:
        add_dir, add_contents_df = checkerboard_inject_parse(
            file_full_path=local_temp_path,
            filename=filename,
            output_dir=output_dir,
            kb_dir=JobMetadataHelper.get_parsing_param(job_metadata, "kb_dir", "Default_Root"),
            doc_type=doc_type,
            smart_title_parse=JobMetadataHelper.get_parsing_param(job_metadata, "smart_title_parse", True),
            summary_image=JobMetadataHelper.get_parsing_param(job_metadata, "summary_image", True),
            summary_table=JobMetadataHelper.get_parsing_param(job_metadata, "summary_table", True),
            summary_txt=JobMetadataHelper.get_parsing_param(job_metadata, "summary_txt", True),
            add_frag_desc=JobMetadataHelper.get_parsing_param(job_metadata, "add_frag_desc", ""),
            s3_key=s3_key,
        )
    finally:
        if local_temp_path and os.path.exists(local_temp_path):
            try:
                os.unlink(local_temp_path)
                logger.info(f"Temp file cleaned up: {local_temp_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")

    logger.info(f"File parsing completed: job_id={job_id}, add_dir={add_dir}, chunks={len(add_contents_df) if add_contents_df is not None else 0}")

    if add_contents_df is None:
        raise WorkerHandlingException(
            user_message="We could not extract content from your file",
            internal_message="File parsing failed, no content returned from parser",
        )

    if add_contents_df.empty:
        logger.warning(f"No content returned from file parsing: job_id={job_id}, filename={filename}")

    # Save add_dir to Redis
    metadata_service.update_metadata(job_id, {"add_dir": add_dir})

    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=30,
        message_text="Parse completed, saving chunks...",
    )

    # Save DataFrame as chunks to Redis (sync)
    chunks_redis_service = SyncChunksRedisService(redis_service)

    if add_contents_df is not None:
        success = chunks_redis_service.save_dataframe_as_chunks(job_id, add_contents_df)
        if success:
            logger.info(f"DataFrame saved as chunks to Redis: job_id={job_id}")
        else:
            logger.error(f"Failed to save DataFrame as chunks: job_id={job_id}")
    else:
        chunks_redis_service.save_chunks(job_id, [])

    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=70,
        message_text="Chunks saved, generating zip...",
    )

    # Get chunks data from Redis
    chunks = chunks_redis_service.get_chunks(job_id)
    if chunks:
        logger.info(f"Chunks retrieved: job_id={job_id}, count={len(chunks)}")
    else:
        logger.warning(f"No chunks retrieved: job_id={job_id}")
        chunks = []

    # Get source file name
    source_file_name = JobMetadataHelper.get_field(job_metadata, "source_file_name") or JobMetadataHelper.get_field(job_metadata, "source_url")
    if isinstance(source_file_name, str) and "/" in source_file_name:
        source_file_name = os.path.basename(source_file_name)

    data_id = JobMetadataHelper.get_field(job_metadata, "data_id")

    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=80,
        message_text="Generating ZIP package...",
    )

    # Generate ZIP package
    zip_service = ZipResultService()
    zip_file_path, checksum, statistics, zip_size = zip_service.generate_zip_package(
        job_id=job_id,
        chunks=chunks,
        add_dir=str(add_dir) if add_dir else "",
        source_file_name=source_file_name,
        data_id=data_id,
        job_metadata=job_metadata,
        parsed_df=add_contents_df,
    )

    checksum_value = checksum.get("value", "") if isinstance(checksum, dict) else (checksum or "")

    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=90,
        message_text="Uploading results to S3...",
    )

    # Upload ZIP to S3 (sync)
    result_s3_key = upload_zip_result(job_id, zip_file_path)

    stored_count = 0
    kb_records = []

    message_publisher.publish_progress_update(
        job_id=job_id,
        progress=100,
        message_text="Task complete!",
    )

    # Publish result message
    message_publisher.publish_result(
        job_id=job_id,
        chunks_job_id=job_id,
        result_s3_key=result_s3_key,
        checksum=checksum_value,
        zip_size=zip_size,
        stored_count=stored_count,
        kb_records=kb_records,
        statistics=statistics,
        delivery_mode="url",
        add_dir=str(add_dir) if add_dir else None,
    )

    logger.info(f"Worker processing complete: job_id={job_id}, result_s3_key={result_s3_key}")

    return {
        "status": "success",
        "job_id": job_id,
        "add_dir": add_dir,
        "vectors_count": 0,
        "contents_count": len(add_contents_df) if add_contents_df is not None else 0,
        "stored_count": stored_count,
        "delivery_mode": "url",
        "result_s3_key": result_s3_key,
    }
