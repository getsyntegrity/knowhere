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
from app.repositories.knowledge_base_repository import create_update_kb
from shared.services.messaging.monitoring import message_monitoring
from shared.services.redis import RedisServiceFactory
from shared.services.redis.chunks_redis_service import ChunksRedisService
from shared.services.redis.task_redis_service import TaskRedisService
from app.services.state_machine import JobStateMachine
from app.services.job_lifecycle_service import JobLifecycleService
from loguru import logger
from shared.core.exceptions.domain_exceptions import KnowhereException, WorkerHandlingException
from shared.utils.error_details import normalize_error_details
from shared.core.state_machine.states import is_valid_transition


# Module-level singletons — these services are stateless, no need to
# re-instantiate per message (avoids ~6 object allocations per message).
_state_machine = JobStateMachine()
_lifecycle_service = JobLifecycleService()


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
            result.get("status") in {"success", "ignored"},
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
    state_machine = _state_machine
    
    try:
        async with get_db_context() as db:
            # Only ignore the known poison-message id from parser internals.
            # TODO need clean,
            if message.job_id == "layout_parser":
                logger.warning("Ignore status update for internal parser context id: layout_parser")
                return {
                    "status": "success",
                    "job_id": message.job_id,
                    "ignored": True,
                    "reason": "layout_parser_internal_id",
                }

            current_state = await state_machine.get_current_state(
                db=db,
                job_id=message.job_id,
            )
            if current_state is None:
                logger.warning(
                    f"Job {message.job_id} 状态更新失败: 当前状态不存在"
                )
                return {
                    "status": "failed",
                    "job_id": message.job_id,
                    "reason": "missing_current_state",
                }

            if current_state == message.status:
                logger.info(
                    f"Job {message.job_id} 已处于状态 {message.status}, 跳过重复状态更新"
                )
                return {
                    "status": "success",
                    "job_id": message.job_id,
                    "idempotent": True,
                }

            if not is_valid_transition(current_state, message.status):
                logger.warning(
                    f"忽略过期或非法状态更新: job_id={message.job_id}, "
                    f"current_state={current_state}, requested_state={message.status}, "
                    f"trigger={message.trigger}"
                )
                return {
                    "status": "ignored",
                    "job_id": message.job_id,
                    "reason": "invalid_transition",
                    "current_state": current_state,
                    "requested_state": message.status,
                    "retryable": False,
                }

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
                logger.info(f"Job {message.job_id} 状态更新成功: {current_state} -> {message.status}")
                return {"status": "success", "job_id": message.job_id}

            logger.warning(f"Job {message.job_id} 状态更新失败: {current_state} -> {message.status}")
            return {
                "status": "failed",
                "job_id": message.job_id,
                "reason": "state_transition_failed",
            }
                
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
    state_machine = _state_machine
    
    try:
        async with get_db_context() as db:
            # 1. Fetch chunks (Read only)
            redis_service = RedisServiceFactory.get_service()
            chunks_redis_service = ChunksRedisService(redis_service)
            chunks = await chunks_redis_service.get_chunks(message.chunks_job_id)
            
            if not chunks:
                logger.warning(f"Job {message.job_id} chunks not found")
                chunks = []
            
            # 2. Use JobLifecycleService for Atomic Transaction (Unit of Work)
            lifecycle_service = _lifecycle_service
            inline_payload = {
                "checksum": message.checksum,
            }
            
            result = await lifecycle_service.finalize_job_success(
                db,
                message,
                chunks,
                inline_payload,
            )
            
            return result
            
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
    state_machine = _state_machine
    
    try:
        from typing import cast
        from sqlalchemy.ext.asyncio import AsyncSession
        async with get_db_context() as db_ctx:
            db = cast(AsyncSession, db_ctx)
            
            # Extract error details
            error_code = message.error_code or "UNKNOWN"
            error_details = None
            if message.metadata and message.metadata.get("details"):
                error_details = normalize_error_details(
                    message.metadata.get("details")
                )

            # Check for refund request
            should_refund = False
            if message.metadata and message.metadata.get("refund_credits"):
                 should_refund = True
            
            # Use JobLifecycleService for Atomic Transaction (Unit of Work)
            lifecycle_service = _lifecycle_service
            success = await lifecycle_service.finalize_job_failure(
                db=db,
                job_id=message.job_id,
                error_message=message.error_message,
                error_code=error_code,
                error_details=error_details,
                should_refund=should_refund,
            )
            
            if success:
                logger.info(f"Job {message.job_id} failure handled successfully")
                return {
                    "status": "success",
                    "job_id": message.job_id,
                    "error_code": error_code,
                    "error_message": message.error_message
                }
            else:
                 return {
                    "status": "failed",
                    "job_id": message.job_id,
                    "reason": "Lifecycle service returned false"
                }
                
    except KnowhereException:
        raise
    except Exception as e:
        logger.error(f"Error handling failure message: {e}")
        raise WorkerHandlingException(
            internal_message=f"Error handling failure message: {str(e)}",
            original_exception=e
        )


# Helper functions moved to JobLifecycleService
