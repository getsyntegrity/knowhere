"""
Celery任务定义
迁移自ARQ任务，支持优先级和队列路由
"""
import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from celery import Task
from loguru import logger

from app.core.celery_app import get_celery_app, get_task_priority, get_queue_name
from app.core.celery_router import CeleryTaskRouter, TaskContext, TaskType, UserLevel, DocumentImportance
from app.core.state_machine import JobStateMachine, JobState
from app.services.redis import RedisServiceFactory, TaskRedisService, UserRedisService

# 获取Celery应用
celery_app = get_celery_app()

# 创建路由器实例
task_router = CeleryTaskRouter()

class BaseTask(Task):
    """基础任务类，提供通用功能"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"任务 {task_id} 执行失败: {exc}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试回调"""
        logger.warning(f"任务 {task_id} 重试: {exc}")

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.process_ai_query')
def process_ai_query(self, prompt: str, user_id: str, temperature: float = 0.1, 
                    conversation_id: str = None, **kwargs):
    """
    AI查询任务 - 高优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='ai_query',
            user_id=user_id,
            user_level=kwargs.get('user_level', 'standard'),
            is_urgent=kwargs.get('is_urgent', False),
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '正在连接AI大模型...'})
        
        # 异步执行AI查询
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_process_ai_query_async(
                prompt, user_id, temperature, conversation_id, context
            ))
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"AI查询任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

async def _process_ai_query_async(prompt: str, user_id: str, temperature: float,
                                 conversation_id: str, context: TaskContext):
    """异步AI查询处理"""
    # 获取Redis服务
    redis_service = RedisServiceFactory.get_service()
    task_service = TaskRedisService(redis_service)
    
    # 初始化状态机
    state_machine = JobStateMachine(redis_service)
    
    # 设置任务状态
    await task_service.set_task_status(context.user_id, "正在连接AI大模型...")
    
    # 延迟导入DeepSeek客户端
    from app.utils.DeepSeekClient import DeepSeekRedisStreamClient
    ai_client = DeepSeekRedisStreamClient(redis_service)
    
    # 设置对话ID
    if not conversation_id:
        conversation_id = f"ai_query_{user_id}_{int(time.time())}"
    
    # 执行AI查询
    try:
        logger.debug(f'process_ai_query_async prompt: {prompt}')
        logger.debug(f'process_ai_query_async temperature: {temperature}')
        logger.debug(f'process_ai_query_async conversation_id: {conversation_id}')
        
        # 更新状态为处理中
        await state_machine.set_task_timeout(context.user_id, JobState.PROCESSING.value)
        
        result = await ai_client.chat_completion(
            messages=prompt,
            temperature=temperature,
            conversation_id=conversation_id,
        )
        logger.debug(f'process_ai_query_async result: {result}')
        
        # 保存结果
        await task_service.save_task_result(context.user_id, {
            'result': result,
            'conversation_id': conversation_id,
            'timestamp': time.time()
        })
        
        await task_service.set_task_status(context.user_id, "complete")
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        await task_service.mark_task_failed(context.user_id, str(e))
        raise




