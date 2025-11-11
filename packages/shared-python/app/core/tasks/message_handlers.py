"""
API服务的消息处理器
处理Worker发布的消息并执行相应的数据操作
"""
import asyncio
import traceback
from typing import Dict, Any
from celery import Task
from loguru import logger

from app.core.celery_app import get_celery_app
from app.core.state_machine import JobStateMachine, JobStatus
from app.repositories.job_repository import JobRepository
from app.repositories.job_result_repository import JobResultRepository
from app.repositories.knowledge_base_repository import create_update_kb
from app.models.database.knowledge_base import KBPydantic
from app.core.database import get_db_context
from app.models.schemas.messages import (
    JobStatusUpdateMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobFailureMessage,
)
from app.services.redis import RedisServiceFactory
from app.services.redis.task_redis_service import TaskRedisService
from app.services.redis.chunks_redis_service import ChunksRedisService
from app.services.messaging.monitoring import message_monitoring
import time

# 获取Celery应用
celery_app = get_celery_app()


class MessageHandlerBaseTask(Task):
    """消息处理器基础任务类"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"消息处理任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"消息处理任务 {task_id} 执行失败: {exc}")
        logger.error(f"异常信息: {einfo}")


@celery_app.task(bind=True, base=MessageHandlerBaseTask, name='app.core.tasks.message_handlers.handle_job_status_update')
def handle_job_status_update(self, message_data: Dict[str, Any]):
    """
    处理Job状态更新消息
    
    Args:
        message_data: 消息数据字典
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobStatusUpdateMessage(**message_data)
        
        # 使用异步上下文执行数据库操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_handle_status_update_async(message))
            
            # 记录监控指标
            duration_ms = (time.time() - start_time) * 1000
            message_monitoring.record_message_processed(
                message.message_type,
                message.job_id,
                True,
                duration_ms
            )
            
            return result
        finally:
            loop.close()
            
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
        
        raise self.retry(exc=e, countdown=60, max_retries=3)


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
                
    except Exception as e:
        logger.error(f"处理状态更新消息时出错: {e}")
        raise


@celery_app.task(bind=True, base=MessageHandlerBaseTask, name='app.core.tasks.message_handlers.handle_job_progress_update')
def handle_job_progress_update(self, message_data: Dict[str, Any]):
    """
    处理Job进度更新消息
    
    Args:
        message_data: 消息数据字典
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobProgressUpdateMessage(**message_data)
        
        # 使用异步上下文执行Redis操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_handle_progress_update_async(message))
            
            # 记录监控指标
            duration_ms = (time.time() - start_time) * 1000
            message_monitoring.record_message_processed(
                message.message_type,
                message.job_id,
                result.get('status') == 'success',
                duration_ms
            )
            
            return result
        finally:
            loop.close()
            
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
            
    except Exception as e:
        logger.error(f"处理进度更新消息时出错: {e}")
        raise


@celery_app.task(bind=True, base=MessageHandlerBaseTask, name='app.core.tasks.message_handlers.handle_job_result')
def handle_job_result(self, message_data: Dict[str, Any]):
    """
    处理Job结果数据消息
    
    Args:
        message_data: 消息数据字典
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobResultMessage(**message_data)
        
        # 使用异步上下文执行数据库操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_handle_result_async(message))
            
            # 记录监控指标
            duration_ms = (time.time() - start_time) * 1000
            message_monitoring.record_message_processed(
                message.message_type,
                message.job_id,
                result.get('status') == 'success',
                duration_ms
            )
            
            return result
        finally:
            loop.close()
            
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
        
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _handle_result_async(message: JobResultMessage):
    """异步处理结果数据"""
    job_repo = JobRepository()
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
            
            return {
                "status": "success",
                "job_id": message.job_id,
                "stored_count": message.stored_count
            }
            
    except Exception as e:
        logger.error(f"处理结果消息时出错: {e}")
        raise


@celery_app.task(bind=True, base=MessageHandlerBaseTask, name='app.core.tasks.message_handlers.handle_job_failure')
def handle_job_failure(self, message_data: Dict[str, Any]):
    """
    处理Job失败消息
    
    Args:
        message_data: 消息数据字典
    """
    start_time = time.time()
    try:
        # 解析消息
        message = JobFailureMessage(**message_data)
        
        # 使用异步上下文执行数据库操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_handle_failure_async(message))
            
            # 记录监控指标
            duration_ms = (time.time() - start_time) * 1000
            message_monitoring.record_message_processed(
                message.message_type,
                message.job_id,
                result.get('status') == 'success',
                duration_ms
            )
            
            return result
        finally:
            loop.close()
            
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
        
        raise self.retry(exc=e, countdown=60, max_retries=3)


async def _handle_failure_async(message: JobFailureMessage):
    """异步处理失败消息"""
    state_machine = JobStateMachine()
    
    try:
        async with get_db_context() as db:
            # 更新Job状态为失败
            success = await state_machine.mark_failed(
                db,
                message.job_id,
                message.error_message
            )
            
            if success:
                logger.info(f"Job {message.job_id} 标记为失败: {message.error_message}")
                
                # 记录详细错误信息
                if message.stack_trace:
                    logger.error(f"Job {message.job_id} 堆栈跟踪:\n{message.stack_trace}")
                
                return {
                    "status": "success",
                    "job_id": message.job_id,
                    "error_message": message.error_message
                }
            else:
                logger.warning(f"Job {message.job_id} 标记失败状态失败")
                return {
                    "status": "failed",
                    "job_id": message.job_id,
                    "reason": "状态更新失败"
                }
                
    except Exception as e:
        logger.error(f"处理失败消息时出错: {e}")
        raise

