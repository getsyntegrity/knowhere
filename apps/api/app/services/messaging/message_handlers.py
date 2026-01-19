"""
API服务的消息处理器
处理Worker发布的消息并执行相应的数据操作
"""
import time
from typing import Any, Dict

from shared.core.database import get_db_context
from shared.models.database.knowledge_base import KBPydantic
from shared.models.schemas.messages import (JobFailureMessage,
                                         JobProgressUpdateMessage,
                                         JobResultMessage,
                                         JobStatusUpdateMessage)
from app.repositories.job_result_repository import JobResultRepository
from app.repositories.knowledge_base_repository import create_update_kb
from shared.services.messaging.monitoring import message_monitoring
from shared.services.redis import RedisServiceFactory
from shared.services.redis.chunks_redis_service import ChunksRedisService
from shared.services.redis.task_redis_service import TaskRedisService
from app.services.state_machine import JobStateMachine
from loguru import logger
from shared.core.exceptions.domain_exceptions import KnowhereException, WorkerHandlingException


async def handle_job_status_update(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理Job状态更新消息（供MessageConsumer直接调用）
    
    Args:
        message_data: 消息数据字典
        
    Returns:
        Dict: 处理结果
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobStatusUpdateMessage(**message_data)
        
        # 执行异步处理
        result = await _handle_status_update_async(message)
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        message_monitoring.record_message_processed(
            message.message_type,
            message.job_id,
            True,
            duration_ms
        )
        
        return result
        
    except Exception as e:
        logger.error(f"处理状态更新消息失败: {e}")
        logger.error(f"消息数据: {message_data}")
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        job_id = message_data.get('job_id', 'unknown')
        message_monitoring.record_message_processed(
            'job_status_update',
            job_id,
            False,
            duration_ms
        )
        
        if isinstance(e, KnowhereException):
            raise
        raise WorkerHandlingException(
            internal_message=f"处理状态更新消息失败: {str(e)}",
            original_exception=e
        )


async def _handle_status_update_async(message: JobStatusUpdateMessage):
    """异步处理状态更新"""
    state_machine = JobStateMachine()
    
    try:
        async with get_db_context() as db:
            # 执行状态转换
            success = await state_machine.transition(
                db=db,
                job_id=message.job_id,
                to_state=message.status,
                transition_reason=message.trigger,
                operator_id=message.operator_id,
                operator_type=message.operator_type,
                metadata=message.metadata
            )
            
            if success:
                logger.info(f"Job {message.job_id} 状态更新成功: {message.previous_status} -> {message.status}")
                return {"status": "success", "job_id": message.job_id}
            else:
                logger.warning(f"Job {message.job_id} 状态更新失败")
                return {"status": "failed", "job_id": message.job_id, "reason": "状态转换失败"}
                
    except KnowhereException:
        raise
    except Exception as e:
        logger.error(f"处理状态更新消息时出错: {e}")
        raise WorkerHandlingException(
            internal_message=f"处理状态更新消息时出错: {str(e)}",
            original_exception=e
        )


async def handle_job_progress_update(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理Job进度更新消息（供MessageConsumer直接调用）
    
    Args:
        message_data: 消息数据字典
        
    Returns:
        Dict: 处理结果
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobProgressUpdateMessage(**message_data)
        
        # 执行异步处理
        result = await _handle_progress_update_async(message)
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        message_monitoring.record_message_processed(
            message.message_type,
            message.job_id,
            result.get('status') == 'success',
            duration_ms
        )
        
        return result
        
    except Exception as e:
        logger.error(f"处理进度更新消息失败: {e}")
        logger.error(f"消息数据: {message_data}")
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        job_id = message_data.get('job_id', 'unknown')
        message_monitoring.record_message_processed(
            'job_progress_update',
            job_id,
            False,
            duration_ms
        )
        
        # 进度更新失败不应该重试，只记录日志
        return {"status": "failed", "error": str(e)}


async def _handle_progress_update_async(message: JobProgressUpdateMessage):
    """异步处理进度更新"""
    try:
        redis_service = RedisServiceFactory.get_service()
        task_service = TaskRedisService(redis_service)
        
        # 更新Redis中的进度信息
        success = await task_service.update_task_progress(
            message.job_id,
            message.progress,
            message.message
        )
        
        if success:
            logger.debug(f"Job {message.job_id} 进度更新成功: {message.progress}% - {message.message}")
            return {"status": "success", "job_id": message.job_id, "progress": message.progress}
        else:
            logger.warning(f"Job {message.job_id} 进度更新失败")
            return {"status": "failed", "job_id": message.job_id}
            
    except KnowhereException:
        raise
    except Exception as e:
        logger.error(f"处理进度更新消息时出错: {e}")
        raise WorkerHandlingException(
            internal_message=f"处理进度更新消息时出错: {str(e)}",
            original_exception=e
        )


async def handle_job_result(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理Job结果数据消息（供MessageConsumer直接调用）
    
    Args:
        message_data: 消息数据字典
        
    Returns:
        Dict: 处理结果
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobResultMessage(**message_data)
        
        # 执行异步处理
        result = await _handle_result_async(message)
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        message_monitoring.record_message_processed(
            message.message_type,
            message.job_id,
            result.get('status') == 'success',
            duration_ms
        )
        
        return result
        
    except Exception as e:
        logger.error(f"处理结果消息失败: {e}")
        logger.error(f"消息数据: {message_data}")
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        job_id = message_data.get('job_id', 'unknown')
        message_monitoring.record_message_processed(
            'job_result',
            job_id,
            False,
            duration_ms
        )
        
        if isinstance(e, KnowhereException):
            raise
        raise WorkerHandlingException(
            internal_message=f"处理结果消息失败: {str(e)}",
            original_exception=e
        )


async def _handle_result_async(message: JobResultMessage):
    """异步处理结果数据"""
    state_machine = JobStateMachine()
    
    try:
        async with get_db_context() as db:
            # 1. 存储知识库数据
            if message.kb_records and len(message.kb_records) > 0:
                kb_records = []
                for record_data in message.kb_records:
                    kb_record = KBPydantic(**record_data)
                    kb_records.append(kb_record)
                
                if kb_records:
                    await create_update_kb(kb_records)
                    logger.info(f"Job {message.job_id} 知识库数据存储成功: {len(kb_records)} 条记录")
            
            # 2. 从Redis获取chunks数据
            redis_service = RedisServiceFactory.get_service()
            chunks_redis_service = ChunksRedisService(redis_service)
            chunks = await chunks_redis_service.get_chunks(message.chunks_job_id)
            
            if not chunks:
                logger.warning(f"Job {message.job_id} 未找到chunks数据")
                chunks = []
            
            # 3. 存储JobResult
            job_result_repo = JobResultRepository()
            inline_payload = {
                "checksum": message.checksum,
            }
            
            job_result = await job_result_repo.upsert_job_result(
                db,
                job_id=message.job_id,
                delivery_mode=message.delivery_mode,
                document_metadata=None,
                inline_payload=inline_payload,
                result_s3_key=message.result_s3_key,
                result_size=message.zip_size
            )
            
            # 4. 存储Chunks
            await job_result_repo.replace_chunks(db, job_result.id, chunks)
            
            # 5. 更新Job状态为完成
            await state_machine.mark_completed(
                db,
                message.job_id,
                {
                    "storage_completed": True,
                    "stored_count": message.stored_count,
                    "delivery_mode": message.delivery_mode
                }
            )
            
            # 6. 清理Redis中的chunks数据
            await chunks_redis_service.delete_chunks(message.chunks_job_id)
            
            logger.info(f"Job {message.job_id} 结果存储完成: stored_count={message.stored_count}")
            
            # 7. 处理Webhook和邮件发送（如果启用）
            await _handle_job_completion_notifications(db, message.job_id, job_result)
            
            return {
                "status": "success",
                "job_id": message.job_id,
                "stored_count": message.stored_count
            }
            
    except KnowhereException:
        raise
    except Exception as e:
        logger.error(f"处理结果消息时出错: {e}")
        raise WorkerHandlingException(
            internal_message=f"处理结果消息时出错: {str(e)}",
            original_exception=e
        )


async def handle_job_failure(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理Job失败消息（供MessageConsumer直接调用）
    
    Args:
        message_data: 消息数据字典
        
    Returns:
        Dict: 处理结果
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobFailureMessage(**message_data)
        
        # 执行异步处理
        result = await _handle_failure_async(message)
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        message_monitoring.record_message_processed(
            message.message_type,
            message.job_id,
            result.get('status') == 'success',
            duration_ms
        )
        
        return result
        
    except Exception as e:
        logger.error(f"处理失败消息失败: {e}")
        logger.error(f"消息数据: {message_data}")
        
        # 记录监控指标
        duration_ms = (time.time() - start_time) * 1000
        job_id = message_data.get('job_id', 'unknown')
        message_monitoring.record_message_processed(
            'job_failure',
            job_id,
            False,
            duration_ms
        )
        
        if isinstance(e, KnowhereException):
            raise
        raise WorkerHandlingException(
            internal_message=f"处理失败消息失败: {str(e)}",
            original_exception=e
        )


async def _handle_failure_async(message: JobFailureMessage):
    """Async handle failure message"""
    state_machine = JobStateMachine()
    
    try:
        from typing import cast
        from sqlalchemy.ext.asyncio import AsyncSession
        async with get_db_context() as db_ctx:
            db = cast(AsyncSession, db_ctx)
            
            # Get error_code from message (defaults to "UNKNOWN" if not provided)
            error_code = message.error_code or "UNKNOWN"
            
            # Extract error_details from metadata (structured data like violations, retry_after)
            error_details = None
            if message.metadata and message.metadata.get("details"):
                error_details = message.metadata.get("details")
            
            # Update Job status to failed with error_code and error_details
            success = await state_machine.mark_failed(
                db,
                message.job_id,
                message.error_message,
                error_code=error_code,
                error_details=error_details
            )
            
            if success:
                logger.info(f"Job {message.job_id} marked as failed: code={error_code}, msg={message.error_message}")
                
                # Check if credits refund is needed
                if message.metadata and message.metadata.get("refund_credits"):
                    try:
                        logger.info(f"Refund request detected: job_id={message.job_id}")
                        from app.services.billing.credits_service import CreditsService
                        from app.repositories.job_repository import JobRepository
                        
                        job_repo = JobRepository()
                        job = await job_repo.get_job_by_id(db, message.job_id)
                        
                        if job:
                            # Refund the actual amount charged (per-page billing)
                            refund_amount = getattr(job, "credits_charged", 0) or 0
                            if refund_amount > 0:
                                credits_service = CreditsService()
                                refund_success = await credits_service.refund_job_credits(
                                    db,
                                    str(job.user_id),
                                    refund_amount,
                                    message.job_id
                                )
                                if refund_success:
                                    logger.info(f"Credits refund successful: job_id={message.job_id}, amount={refund_amount}")
                                else:
                                    logger.info(f"Credits refund skipped (already refunded): job_id={message.job_id}")
                    except Exception as e:
                        logger.error(f"Credits refund failed: {e}", exc_info=True)
                
                # Log detailed error information
                if message.stack_trace:
                    logger.error(f"Job {message.job_id} stack trace:\n{message.stack_trace}")
                
                # Handle failure webhook and email notifications (if enabled)
                await _handle_job_failure_notifications(db, message.job_id, message.error_message, message.error_type, error_code)
                
                return {
                    "status": "success",
                    "job_id": message.job_id,
                    "error_code": error_code,
                    "error_message": message.error_message
                }
            else:
                logger.warning(f"Job {message.job_id} failed to mark as failed")
                return {
                    "status": "failed",
                    "job_id": message.job_id,
                    "reason": "Status update failed"
                }
                
    except KnowhereException:
        raise
    except Exception as e:
        logger.error(f"Error handling failure message: {e}")
        raise WorkerHandlingException(
            internal_message=f"Error handling failure message: {str(e)}",
            original_exception=e
        )


async def _handle_job_completion_notifications(db, job_id: str, job_result: Any):
    """处理Job完成的通知（Webhook和邮件）"""
    try:
        from shared.models.schemas.job_metadata import JobMetadataHelper
        from app.repositories.job_repository import JobRepository
        from app.services.email.job_email_service import JobEmailService
        from shared.services.redis import JobMetadataService, RedisServiceFactory
        from app.services.webhook.webhook_handler_service import \
            WebhookHandlerService
        
        job_repo = JobRepository()
        job = await job_repo.get_job_by_id(db, job_id)
        
        if not job:
            logger.warning(f"Job {job_id} 不存在，跳过通知")
            return
        
        # 检查是否需要发送Webhook
        webhook_enabled = job.webhook_enabled
        webhook_url = job.webhook_url
        
        if webhook_enabled and webhook_url:
            # 从job_metadata获取webhook配置
            redis_service = RedisServiceFactory.get_service()
            metadata_service = JobMetadataService(redis_service)
            job_metadata = await metadata_service.get_metadata(job_id)
            
            if job_metadata:
                webhook_config = JobMetadataHelper.get_webhook(job_metadata)
                if webhook_config and webhook_config.get("url"):
                    webhook_url = webhook_config["url"]
            
            # 发送Webhook
            webhook_handler = WebhookHandlerService()
            webhook_result = await webhook_handler.handle_job_completion_webhook(
                db=db,
                job_id=job_id,
                job_result=job_result,
                webhook_url=webhook_url
            )
            logger.info(f"Job完成Webhook发送结果: job_id={job_id}, result={webhook_result}")
        
        # 发送邮件（如果需要）
        try:
            from shared.models.database.user import User
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            
            if user and user.email:
                email_service = JobEmailService()
                email_result = await email_service.send_job_completion_email(
                    db=db,
                    job_id=job_id,
                    job_result=job_result,
                    user_email=user.email,
                    user_name=getattr(user, 'full_name', None) or user.email,
                    job_type=job.job_type or "kb_management"
                )
                logger.info(f"Job完成邮件发送结果: job_id={job_id}, user_email={user.email}, result={email_result}")
        except Exception as e:
            logger.error(f"发送Job完成邮件失败: {e}")
        
    except Exception as e:
        logger.error(f"处理Job完成通知失败: {e}")


async def _handle_job_failure_notifications(db, job_id: str, error_message: str, error_type: str = None, error_code: str = "UNKNOWN"):
    """Handle Job failure notifications (Webhook and email)"""
    try:
        from app.repositories.job_repository import JobRepository
        from app.services.email.job_email_service import JobEmailService
        from app.services.webhook.webhook_handler_service import \
            WebhookHandlerService
        
        job_repo = JobRepository()
        job = await job_repo.get_job_by_id(db, job_id)
        
        if not job:
            logger.warning(f"Job {job_id} does not exist, skipping notification")
            return
        
        # Check if webhook notification is needed
        if job.webhook_enabled and job.webhook_url:
            webhook_handler = WebhookHandlerService()
            webhook_result = await webhook_handler.handle_job_failure_webhook(
                db=db,
                job_id=job_id,
                error_message=error_message,
                error_type=error_type,
                error_code=error_code,
                webhook_url=job.webhook_url
            )
            logger.info(f"Job failure webhook result: job_id={job_id}, result={webhook_result}")
        
        # 发送邮件（如果需要）
        try:
            from shared.models.database.user import User
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            
            if user and user.email:
                email_service = JobEmailService()
                email_result = await email_service.send_job_failure_email(
                    db=db,
                    job_id=job_id,
                    user_email=user.email,
                    error_message=error_message,
                    user_name=getattr(user, 'full_name', None) or user.email,
                    job_type=job.job_type or "kb_management"
                )
                logger.info(f"Job失败邮件发送结果: job_id={job_id}, user_email={user.email}, result={email_result}")
        except Exception as e:
            logger.error(f"发送Job失败邮件失败: {e}")
        
    except Exception as e:
        logger.error(f"处理Job失败通知失败: {e}")

