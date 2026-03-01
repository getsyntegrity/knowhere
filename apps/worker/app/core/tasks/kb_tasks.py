"""
Knowledge Base Management Celery Tasks
"""
import asyncio
import os
import tempfile
import traceback
import uuid
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import httpx
from celery import Task
from loguru import logger
from sqlalchemy import select

from shared.core.celery_app import get_celery_app
from shared.core.state_machine.states import JobStatus
from shared.services.redis import RedisServiceFactory, JobInfoRedisService, JobMetadataService
from shared.services.storage.file_upload_service import FileUploadService
from shared.core.config import settings
from shared.services.messaging import get_message_publisher
from shared.core.async_utils import run_async_task

# Exception handling
from shared.core.exceptions.domain_exceptions import (
    ValidationException,
    FileSystemException,
    NotFoundException,
    StorageServiceException,
    UnknownException,
    WorkerHandlingException,
    SystemSettingMissingException,
    SystemSettingInvalidException,
    InsufficientCreditsException
)
from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.core.exceptions import RETRYABLE_EXCEPTIONS

# Clean top-level imports (concerns #2 & #3)
from shared.core.constants.system import SystemConstants
from shared.core.database import get_db_context
from shared.core.billing import BillingCalculator
from shared.models.database.job import Job
from shared.models.schemas.job_metadata import JobMetadataHelper
from shared.services.redis.chunks_redis_service import ChunksRedisService
from shared.services.storage.zip_result_service import ZipResultService
from app.services.workload.page_estimator import PageEstimator
from app.services.document_parser.parse_service import checkerboard_inject_parse
from shared.services.billing import CreditsService

# Get Celery application
celery_app = get_celery_app()


class KBBaseTask(Task):
    """Knowledge Base base task class - provides centralized exception handling"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Task success callback"""
        logger.info(f"KB task {task_id} completed successfully")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Task failure callback - Centralized exception handling.
        
        This is a built-in Celery method, automatically called when a task raises an exception.
        """
        # Extract job_id from args or kwargs
        job_id = self._extract_job_id(args, kwargs)
        request_id = str(uuid.uuid4())
        
        # Normalize to KnowhereException
        knowhere_exc = exc if isinstance(exc, KnowhereException) else UnknownException(original_exception=exc)
        
        # Log based on severity
        log_data = knowhere_exc.to_log()
        if knowhere_exc.http_status_code >= 500:
            logger.bind(**log_data).error(
                f"[{task_id}] System Error: {knowhere_exc.code.value} - {knowhere_exc.internal_message}"
            )
            
            # Log KnowhereException traceback
            if knowhere_exc.__traceback__:
                exc_tb = "".join(traceback.format_exception(type(knowhere_exc), knowhere_exc, knowhere_exc.__traceback__))
                logger.error(f"[{task_id}] KnowhereException traceback:\n{exc_tb}")
            
            # Log original exception traceback if wrapped
            if knowhere_exc.original_exception and knowhere_exc.original_exception.__traceback__:
                orig_tb = "".join(traceback.format_exception(
                    type(knowhere_exc.original_exception),
                    knowhere_exc.original_exception,
                    knowhere_exc.original_exception.__traceback__
                ))
                logger.error(f"[{task_id}] Original exception traceback:\n{orig_tb}")
        else:
            logger.bind(**log_data).warning(
                f"[{task_id}] Client Error: {knowhere_exc.code.value} - {knowhere_exc.internal_message}"
            )
        
        # Get error info from to_client (reuse the same format)
        client_response = knowhere_exc.to_client(request_id)
        error_info = client_response["error"]  # Extract just the error field
        
        # Publish failure message
        if job_id:
            try:
                message_publisher = get_message_publisher()
                
                # Include stack trace only for wrapped exceptions
                stack_trace = str(einfo) if knowhere_exc.original_exception else None
                
                run_async_task(
                    message_publisher.publish_failure(
                        job_id=job_id,
                        error_message=error_info["message"],
                        error_code=error_info["code"],
                        error_type=type(exc).__name__,
                        stack_trace=stack_trace,
                        metadata={
                            "refund_credits": True,
                            "details": error_info.get("details"),
                        }
                    )
                )
                logger.info(f"Failure message published: job_id={job_id}, error_code={error_info['code']}")
            except Exception as e:
                logger.error(f"Failed to publish failure message: job_id={job_id}, error={e}")
    
    def _extract_job_id(self, args, kwargs) -> Optional[str]:
        """Extract job_id from args or kwargs"""
        if args and len(args) > 0:
            if isinstance(args[0], dict) and 'job_id' in args[0]:
                return args[0]['job_id']
            elif isinstance(args[0], str):
                return args[0]
        if 'job_id' in kwargs:
            return kwargs['job_id']
        return None
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Task retry callback - publishes retry status to API service"""
        logger.warning(f"KB task {task_id} retrying: {exc}")
        
        job_id = self._extract_job_id(args, kwargs)
        
        if job_id:
            # Publish retry message to notify API service
            try:
                message_publisher = get_message_publisher()
                run_async_task(
                    message_publisher.publish_status_update(
                        job_id=job_id,
                        status=JobStatus.RUNNING.value,  # Keep running status during retry
                        trigger="task_retry",
                        metadata={
                            "retry_count": self.request.retries,
                            "error_message": str(exc),
                            "task_id": task_id
                        },
                        operator_type="system"
                    )
                )
                logger.info(f"Retry message published: job_id={job_id}, retry_count={self.request.retries}")
            except Exception as e:
                logger.error(f"Failed to publish retry message: {e}")


# File upload task removed - files are now uploaded directly to S3
@celery_app.task(
    bind=True,
    base=KBBaseTask,
    name='app.core.tasks.kb_tasks.upload_url_file_task',
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'countdown': settings.KB_TASK_RETRY_COUNTDOWN, 'max_retries': settings.KB_TASK_MAX_RETRIES}
)
def upload_url_file_task(self, job_id: str, source_url: str, user_id: str = None, job_type: str = None):
    """Download file from URL and upload to S3"""
    logger.info(f"Task started: task_id={self.request.id}, job_id={job_id}, user_id={user_id}")
    
    if not job_id:
        raise WorkerHandlingException(
            message="An unexpected system error occurred",
            internal_message="Worker task 'upload_url_file_task' called without job_id"
        )

    # Use run_async_task for proper event loop management
    return run_async_task(_upload_url_file_async(
        job_id, source_url, user_id, job_type
    ))


async def _upload_url_file_async(job_id: str, source_url: str, user_id: str, job_type: str = None):
    """Async URL file download and upload to S3"""
    message_publisher = get_message_publisher()
    
    # Get job info from Redis
    redis_service = RedisServiceFactory.get_service()
    job_info_service = JobInfoRedisService(redis_service)
    job_info = await job_info_service.get_job_info(job_id)
    
    if not job_info:
        # If not in Redis, try to get from job_metadata
        metadata_service = JobMetadataService(redis_service)
        job_metadata = await metadata_service.get_metadata(job_id)
        if job_metadata:
            # Extract s3_key from metadata (if exists)
            s3_key = job_metadata.get("s3_key")
        else:
            raise NotFoundException(
                resource="JobInfo",
                resource_id=job_id,
                internal_message="Job info not found in Redis or Metadata"
            )
    else:
        s3_key = job_info.get("s3_key")

    if not s3_key:
        raise NotFoundException(
            resource="JobInfo",
            resource_id='s3_key',
            internal_message=f"Missing s3_key in Redis job info for job_id={job_id}"
        )
    
    # Publish progress: validating file type
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=3,
        message_text="Validating URL file type..."
    )
    
    # Step 1: Validate URL file type (before download, prevent unsafe files)
    parsed_url = urlparse(source_url)
    url_path = parsed_url.path
    file_extension = os.path.splitext(url_path)[1].lower()
    
    # Get supported file extensions
    all_supported_extensions = []
    for category in SystemConstants.SUPPORTED_EXTENSIONS.values():
        all_supported_extensions.extend(category)
    
    if not file_extension or file_extension not in all_supported_extensions:
        supported_formats = ", ".join(sorted(all_supported_extensions))
        raise ValidationException(
            user_message=f"Unsupported file type {file_extension}",
            violations=[{"field": "file_extension", "description": f"Must be one of: {supported_formats}"}]
        )

    # Publish progress: downloading
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=10,
        message_text="Downloading file from URL...",
    )
    
    # Step 2: Download file to temp directory
    try:
        upload_service = FileUploadService()
        temp_file_path = await upload_service._download_file_from_url(source_url)
    except Exception as e:
        raise ValidationException(
            user_message=f"Failed to download file from URL",
            violations=[{"field": "source_url", "description": "Could not download file from the provided URL"}],
            internal_message=f"Failed to download file from URL: {source_url}, error: {e}"
        )
    
    try:
        # Publish progress: validating file size
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=30,
            message_text="Validating file size..."
        )
        
        # Step 3: Validate file size (before S3 upload)
        file_size = os.path.getsize(temp_file_path)
        
        # Determine limit based on extension
        limit = 100 * 1024 * 1024  # Default 100MB (PDF, PPTX)
        if file_extension in ['.docx', '.xlsx', '.doc', '.xls']:
            limit = 50 * 1024 * 1024  # 50MB for DOCX/XLSX
            
        if file_size > limit:
            limit_mb = limit // (1024 * 1024)
            raise ValidationException(
                user_message=f"File size exceeds limit (max {limit_mb}MB for {file_extension})",
                violations=[{"field": "file_size", "description": f"Size {file_size} bytes exceeds limit of {limit} bytes"}]
            )
        
        # Publish progress: uploading to S3
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=50,
            message_text="Uploading file to S3..."
        )
        
        # Step 4: Upload to S3 (using pre-set s3_key from job)
        await upload_service._upload_to_s3(temp_file_path, s3_key, upload_service.uploads_bucket)
        
        logger.info(f"File uploaded to S3: {s3_key}")
        
    finally:
        # Clean up temp file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.debug(f"Temp file cleaned up: {temp_file_path}")
    
    # Publish progress: verifying upload
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=80,
        message_text="Verifying upload result...",
    )
    
    # Step 5: Verify S3 file exists
    file_info = await upload_service.verify_s3_file_exists(s3_key)
    if not file_info.get("exists"):
        raise StorageServiceException(
            message="We failed to verify your file upload",
            internal_message=f"S3 file verification failed for {s3_key}"
        )
    
    # Publish progress: complete
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=100,
        message_text="URL file upload complete, waiting for processing...",
    )
    
    logger.info(f"URL file upload complete, waiting for S3 webhook: {job_id} -> {s3_key}")
    
    return {
        "status": "success",
        "job_id": job_id,
        "s3_key": s3_key,
        "file_size": file_info.get("size")
    }


@celery_app.task(
    bind=True,
    base=KBBaseTask,
    name='app.core.tasks.kb_tasks.parse_task',
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'countdown': settings.KB_TASK_RETRY_COUNTDOWN, 'max_retries': settings.KB_TASK_MAX_RETRIES}
)
def parse_task(self, job_id: str, user_id: str = None, job_type: str = "kb_management"):
    """Parse and vectorize task (file already uploaded to S3)"""
    logger.info(f"Task started: task_id={self.request.id}, job_id={job_id}, user_id={user_id}")
    
    if not job_id:
        raise WorkerHandlingException(
            message="An unexpected system error occurred",
            internal_message="Worker task 'parse_task' called without job_id"
        )
    
    # Use run_async_task for proper event loop management (reusing loop)
    # This keeps the event loop alive effectively
    return run_async_task(_parse_async(
        job_id, user_id
    ))


async def _parse_async(job_id: str, user_id: str):
    """Async parse and vectorize (file already uploaded to S3)"""
    logger.info(f"Async function started: job_id={job_id}, user_id={user_id}")
    message_publisher = get_message_publisher()
    logger.debug(f"Message publisher obtained: job_id={job_id}")
    
    # 从Redis获取Job信息
    logger.info(f"开始获取Redis服务: job_id={job_id}")
    redis_service = RedisServiceFactory.get_service()
    logger.info(f"Redis服务获取成功: job_id={job_id}")
    job_info_service = JobInfoRedisService(redis_service)
    logger.info(f"JobInfoRedisService创建成功，开始获取job_info: job_id={job_id}")
    job_info = await job_info_service.get_job_info(job_id)
    logger.info(f"job_info获取完成: job_id={job_id}, job_info存在={job_info is not None}")
    
    if not job_info:
        raise NotFoundException(
            resource="JobInfo",
            resource_id=job_id,
            internal_message="job info not found in Redis"
        )
    
    s3_key = job_info.get("s3_key")
    logger.info(f"s3_key提取完成: job_id={job_id}, s3_key={s3_key}")
    if not s3_key:
        raise NotFoundException(
            resource="JobInfo",
            resource_id='s3_key',
            internal_message="Missing s3_key in job_info"
        )
    
    job_user_id = job_info.get("user_id")
    if not job_user_id:
        job_user_id = user_id  # 回退到参数中的user_id
    logger.info(f"user_id确定: job_id={job_id}, job_user_id={job_user_id}")
    
    # 验证S3文件存在性
    logger.info(f"开始验证S3文件存在性: job_id={job_id}, s3_key={s3_key}")
    upload_service = FileUploadService()
    logger.info(f"FileUploadService创建成功，开始验证文件: job_id={job_id}")
    file_info = await upload_service.verify_s3_file_exists(s3_key)
    logger.info(f"S3文件验证完成: job_id={job_id}, exists={file_info.get('exists')}")
    if not file_info.get("exists"):
        raise NotFoundException(
            resource="S3File",
            resource_id=s3_key,
            internal_message=f"S3 file not found: {s3_key}"
        )
    
    logger.info(f"S3文件验证成功: {s3_key}")

    # Validate file size
    file_size = file_info.get("size", 0)
    file_extension = os.path.splitext(s3_key)[1].lower()
    
    limit = 100 * 1024 * 1024  # Default 100MB (PDF, PPTX)
    if file_extension in ['.docx', '.xlsx', '.doc', '.xls']:
        limit = 50 * 1024 * 1024  # 50MB for DOCX/XLSX
        
    if file_size > limit:
        limit_mb = limit // (1024 * 1024)
        logger.warning(f"File size check failed: {file_size} > {limit}, ext={file_extension}")
        raise ValidationException(
            user_message=f"File size exceeds limit (max {limit_mb}MB for {file_extension})",
            violations=[{"field": "file_size", "description": f"Size {file_size} bytes exceeds limit of {limit} bytes"}]
        )
    
    # 从job_metadata获取user_config（创建时已初始化）
    logger.info(f"开始获取job_metadata: job_id={job_id}")
    
    metadata_service = JobMetadataService(redis_service)
    job_metadata = await metadata_service.get_metadata(job_id)
    if not job_metadata:
        raise NotFoundException(
            resource="JobMetadata",
            resource_id=job_id,
            internal_message=f"Job metadata not found for job_id={job_id}"
        )

    # use USERS_DATA_PATH + user_id as output directory
    parent_path = settings.USERS_DATA_PATH
    if not parent_path:
        raise SystemSettingMissingException(
            message="System configuration error",
            internal_message="USERS_DATA_PATH not configured"
        )

    if not os.path.isabs(parent_path):
        raise SystemSettingInvalidException(
            message="System configuration error",
            internal_message=f"USERS_DATA_PATH must be absolute path, current value: {parent_path}"
        )

    output_dir = os.path.join(parent_path, f"kb_{job_user_id}", job_id)

    # Ensure output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Output directory ready: {output_dir}")
    except (OSError, PermissionError) as e:
        raise FileSystemException(
            message="System error preparing storage",
            path=output_dir,
            operation="create_directory",
            internal_message=f"Failed to create directory: {output_dir}",
            original_exception=e
        )

    # 发布状态更新消息：开始处理
    logger.info(f"开始发布状态更新消息: job_id={job_id}, status={JobStatus.RUNNING.value}")
    # 注意：状态检查由API服务处理，Worker只负责发布状态更新消息
    await message_publisher.publish_status_update(
        job_id=job_id,
        status=JobStatus.RUNNING.value,
        trigger="start_processing",
        previous_status=None,  # 由API服务确定之前的状态
        operator_type="system",
    )
    logger.info(f"状态更新消息发布成功: job_id={job_id}")
    
    # 发布进度更新消息：开始解析
    logger.info(f"开始发布进度更新消息: job_id={job_id}, progress=10")
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=10,
        message_text="正在解析文档...",
    )
    logger.info(f"进度更新消息发布成功: job_id={job_id}")
    
    logger.info(f"开始下载文件: S3键={s3_key}, bucket={settings.S3_BUCKET_NAME}")
    
    # 下载文件到本地临时目录
    upload_service = FileUploadService()
    logger.info(f"FileUploadService创建成功，开始生成下载URL: s3_key={s3_key}")
    file_url_response = await upload_service.generate_download_url(s3_key, settings.S3_BUCKET_NAME)
    logger.info(f"下载URL生成成功: job_id={job_id}")
    file_url = file_url_response["download_url"]  # 提取实际的URL字符串
    logger.info(f"提取下载URL完成: job_id={job_id}, url长度={len(file_url) if file_url else 0}")
    
    # 准备解析参数 - 从job_metadata获取
    logger.info(f"开始准备解析参数: job_id={job_id}")
    filename = JobMetadataHelper.get_field(job_metadata, "source_file_name")
    logger.info(f"filename提取完成: job_id={job_id}, filename={filename}")

    # ============================================================
    # FILE DOWNLOAD & WORKLOAD ESTIMATION & SYNC BILLING
    # Download file, estimate pages, BLOCK and call API to charge.
    # If billing fails, stop immediately - do not process.
    # ============================================================
    
    logger.info(f"Starting file download: job_id={job_id}")
    local_temp_path = None
    page_count = 1  # Default minimum
    
    # Download file to temp location (KEEP for reuse in parsing)
    file_ext = os.path.splitext(filename)[1].lower() if filename else ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        local_temp_path = tmp_file.name
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(file_url)
            response.raise_for_status()
            tmp_file.write(response.content)
    
    logger.info(f"File download complete: job_id={job_id}, local_path={local_temp_path}")
    
    # Estimate workload (page count) for this document
    page_count = PageEstimator.estimate(local_temp_path)
    logger.info(f"Workload estimation complete: job_id={job_id}, page_count={page_count}")
    
    # ============================================================
    # SYNCHRONOUS BILLING - Deduct credits before processing
    # ============================================================
    # Use task-local db context to avoid event loop issues with Celery retries
    async with get_db_context() as db:
        # Lock job row to prevent race conditions
        job_result = await db.execute(
            select(Job).where(Job.job_id == job_id).with_for_update()
        )
        job = job_result.scalar_one_or_none()
        
        # Idempotency: already charged
        if job and getattr(job, "billing_status", "") == "charged":
            logger.info(f"Job already charged: {job_id}")
        else:
            # Calculate billing using BillingCalculator
            billing_calc = BillingCalculator()
            micro_dollar_required = billing_calc.calculate_page_cost(page_count)
            
            # Deduct credits using shared service
            try:
                credits_service = CreditsService()
                new_balance = await credits_service.deduct_credits(
                    session=db,
                    user_id=job_user_id,
                    amount=micro_dollar_required.amount,
                    reason=billing_calc.format_description(page_count, filename)
                )
                
                # Update job billing info
                if job:
                    job.page_count = page_count
                    job.credits_charged = micro_dollar_required.amount
                    job.billing_status = "charged"
                
                await db.commit()
                logger.info(f"Billing successful: job_id={job_id}, credits_charged={micro_dollar_required.amount}, new_balance={new_balance}")
                
            except InsufficientCreditsException as e:
                logger.error(f"Billing failed: job_id={job_id}, user_id={job_user_id}")
                if local_temp_path and os.path.exists(local_temp_path):
                    os.unlink(local_temp_path)
                
                # Mark billing status as failed
                if job:
                    job.billing_status = "billing_failed"
                    await db.commit()
                
                # Re-raise with enhanced error message
                raise InsufficientCreditsException(
                    user_message=f"Insufficient credits to process this document ({page_count} pages required, cost: {micro_dollar_required.to_credit()}).",
                    required_credits=micro_dollar_required.to_credit(),
                    internal_message=f"job_id={job_id}, user_id={job_user_id}, page_count={page_count}, required_credits={micro_dollar_required.amount}"
                )
    
    # Store in Redis
    await metadata_service.update_metadata(job_id, {
        "page_count": page_count,
        "billing_status": "charged"
    })
    # ============================================================
    # END BILLING
    # ============================================================

    
    # 调用修改后的解析逻辑（传入user_config）
    # IMPORTANT: Use local_temp_path (already downloaded) to avoid downloading twice
    logger.info(f"开始导入解析服务: job_id={job_id}")
    
    logger.info(f"解析服务导入成功: job_id={job_id}")
    
    doc_type = JobMetadataHelper.get_parsing_param(job_metadata, 'doc_type', 'auto')
    logger.info(f"start parse: job_id={job_id}, filename={filename}, 类型={doc_type}, local_path={local_temp_path}")
    
    try:
        add_dir, add_contents_df = await checkerboard_inject_parse(
            file_full_path=local_temp_path,
            filename=filename,
            output_dir=output_dir,
            kb_dir=JobMetadataHelper.get_parsing_param(job_metadata, "kb_dir", "Default_Root"),
            doc_type=JobMetadataHelper.get_parsing_param(job_metadata, "doc_type", "auto"),
            smart_title_parse=JobMetadataHelper.get_parsing_param(job_metadata, "smart_title_parse", True),
            summary_image=JobMetadataHelper.get_parsing_param(job_metadata, "summary_image", True),
            summary_table=JobMetadataHelper.get_parsing_param(job_metadata, "summary_table", True),
            summary_txt=JobMetadataHelper.get_parsing_param(job_metadata, "summary_txt", False),
            add_frag_desc=JobMetadataHelper.get_parsing_param(job_metadata, "add_frag_desc", ""),
        )
    finally:
        # Cleanup temp file after parsing (success or failure)
        if local_temp_path and os.path.exists(local_temp_path):
            try:
                os.unlink(local_temp_path)
                logger.info(f"Temp file cleaned up: {local_temp_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
    
    logger.info(f"File parsing completed: job_id={job_id}, add_dir={add_dir}, add_contents_df length={len(add_contents_df) if add_contents_df is not None else 0}")
    
    if add_contents_df is None:
        logger.error(f"File parsing failed, no content returned: job_id={job_id}, filename={filename}")
        raise WorkerHandlingException(
            message="We could not extract content from your file",
            internal_message="File parsing failed, no content returned from parser"
        )

    if add_contents_df.empty:
        logger.warning(f"no content returned from file parsing: job_id={job_id}, filename={filename}")
    
    logger.info(f"文件解析成功: job_id={job_id}, add_dir={add_dir}")
    
    # 保存add_dir到Redis job_metadata（用于后续ZIP生成和调试）
    logger.info(f"开始保存add_dir到Redis: job_id={job_id}, add_dir={add_dir}")
    await metadata_service.update_metadata(job_id, {"add_dir": add_dir})
    logger.info(f"add_dir已保存到Redis job_metadata: job_id={job_id}, add_dir={add_dir}")
    
    logger.info(f"开始发布进度更新消息（保存chunks): job_id={job_id}, progress=50")
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=30,
        message_text="parse completed, saving chunks...",
    )
    
    # 保存DataFrame为chunks到Redis
    
    chunks_redis_service = ChunksRedisService(redis_service)
    
    if add_contents_df is not None:
        logger.debug(f"开始保存DataFrame为chunks: DataFrame长度={len(add_contents_df)}")
        success = await chunks_redis_service.save_dataframe_as_chunks(job_id, add_contents_df)
        if success:
            logger.info(f"DataFrame已保存为chunks到Redis: job_id={job_id}")
        else:
            logger.error(f"保存DataFrame为chunks失败: job_id={job_id}")
    else:
        logger.warning("add_contents_df为空，保存空chunks到Redis")
        await chunks_redis_service.save_chunks(job_id, [])
    
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=70,
        message_text="chunks saved, generating zip...",
    )
    
    # 从Redis获取chunks数据（用于生成ZIP包）
    chunks = await chunks_redis_service.get_chunks(job_id)
    if chunks:
        logger.info(f"从Redis获取chunks数据成功: job_id={job_id}, count={len(chunks)}")
    else:
        logger.warning(f"从Redis获取chunks数据失败: job_id={job_id}")
        chunks = []

    # 从job_metadata获取信息
    source_file_name = JobMetadataHelper.get_field(job_metadata, "source_file_name") or JobMetadataHelper.get_field(job_metadata, "source_url")
    if isinstance(source_file_name, str) and "/" in source_file_name:
        source_file_name = os.path.basename(source_file_name)
    
    # 获取 data_id
    data_id = JobMetadataHelper.get_field(job_metadata, "data_id")
    
    # 发布进度更新消息：生成ZIP包
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=80,
        message_text="正在生成ZIP包...",
    )
    
    # 生成 ZIP 包（业务逻辑处理）
    zip_service = ZipResultService()
    zip_file_path, checksum, statistics, zip_size = zip_service.generate_zip_package(
        job_id=job_id,
        chunks=chunks,
        add_dir=add_dir,
        source_file_name=source_file_name,
        data_id=data_id,
        job_metadata=job_metadata,
        parsed_df=add_contents_df,  # Enable kb.csv and hierarchy.json generation
    )
    
    # 提取 checksum 的字符串值（ZipResultService 返回的是字典格式）
    checksum_value = checksum.get("value") if isinstance(checksum, dict) else checksum
    
    # 发布进度更新消息：上传ZIP到S3
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=90,
        message_text="正在上传结果到S3...",
    )
    
    # 上传 ZIP 包到 S3（业务逻辑处理）
    result_s3_key = await upload_service.upload_zip_result(job_id, zip_file_path)
    
    stored_count = 0
    kb_records = []

    # 发布进度更新消息：任务完成
    await message_publisher.publish_progress_update(
        job_id=job_id,
        progress=100,
        message_text="任务完成！",
    )
    
    # 发布结果消息（包含所有需要存储的数据）
    await message_publisher.publish_result(
        job_id=job_id,
        chunks_job_id=job_id,  # chunks数据通过job_id从Redis读取
        result_s3_key=result_s3_key,
        checksum=checksum_value,  # 使用提取的字符串值
        zip_size=zip_size,
        stored_count=stored_count,
        kb_records=kb_records,  # 知识库记录数据
        statistics=statistics,
        delivery_mode="url",
        add_dir=add_dir,
    )
    
    logger.info(f"Worker处理完成，结果消息已发布: job_id={job_id}, stored_count={stored_count}, result_s3_key={result_s3_key}")
    
    return {
        "status": "success",
        "job_id": job_id,
        "add_dir": add_dir,
        "vectors_count": 0,
        "contents_count": len(add_contents_df) if add_contents_df is not None else 0,
        "stored_count": stored_count,
        "delivery_mode": "url",
        "result_s3_key": result_s3_key
    }
