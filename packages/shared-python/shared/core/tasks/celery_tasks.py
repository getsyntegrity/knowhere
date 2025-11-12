"""
Celery任务定义
迁移自ARQ任务，支持优先级和队列路由
"""
import asyncio
import time

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.celery_router import (
    CeleryTaskRouter,
    TaskContext,
)
from shared.core.state_machine.states import JobStatus  # 仅用于状态常量
from shared.services.messaging import get_message_publisher
from shared.services.messaging.message_publisher import run_async_publish
from shared.services.redis import RedisServiceFactory, TaskRedisService

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

@celery_app.task(bind=True, base=BaseTask, name='shared.core.tasks.celery_tasks.process_ai_query')
def process_ai_query(self, prompt: str, user_id: str, temperature: float = 0.1, 
                    conversation_id: str = None, **kwargs):
    """
    AI查询任务 - 高优先级
    """
    logger.info(f"🚀 [Celery Worker] AI查询任务开始: task_id={self.request.id}, user_id={user_id}")
    logger.debug(f"[Celery Worker] 任务参数: temperature={temperature}, conversation_id={conversation_id}")
    
    try:
        # 创建任务上下文
        logger.debug("[Celery Worker] 正在创建任务上下文...")
        context = task_router.create_task_context(
            task_type='ai_query',
            user_id=user_id,
            user_level=kwargs.get('user_level', 'standard'),
            is_urgent=kwargs.get('is_urgent', False),
            metadata=kwargs
        )
        logger.debug(f"[Celery Worker] 任务上下文创建完成: priority={context.priority}")
        
        # 更新任务状态
        logger.debug("[Celery Worker] 更新Celery任务状态...")
        self.update_state(state='PROGRESS', meta={'status': '正在连接AI大模型...'})
        logger.debug("[Celery Worker] Celery任务状态已更新")
        
        # 异步执行AI查询
        logger.info("[Celery Worker] 创建事件循环，准备执行异步AI查询...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("[Celery Worker] 事件循环已创建")
        
        try:
            logger.info("[Celery Worker] 开始执行异步AI查询...")
            result = loop.run_until_complete(_process_ai_query_async(
                prompt, user_id, temperature, conversation_id, context
            ))
            logger.info(f"✅ [Celery Worker] AI查询任务完成: status={result.get('status')}")
            return result
        finally:
            logger.debug("[Celery Worker] 关闭事件循环")
            loop.close()
            
    except Exception as e:
        logger.error(f"❌ [Celery Worker] AI查询任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

async def _process_ai_query_async(prompt: str, user_id: str, temperature: float,
                                 conversation_id: str, context: TaskContext):
    """异步AI查询处理"""
    logger.info("[Celery Worker Async] 进入异步处理函数")
    
    # 获取Redis服务
    logger.debug("[Celery Worker Async] 获取Redis服务...")
    redis_service = RedisServiceFactory.get_service()
    task_service = TaskRedisService(redis_service)
    message_publisher = get_message_publisher()
    
    # 设置任务状态
    logger.debug("[Celery Worker Async] 设置任务状态到Redis...")
    await task_service.set_task_status(context.user_id, "正在连接AI大模型...")
    logger.debug("[Celery Worker Async] 任务状态已设置")
    
    # 延迟导入DeepSeek客户端
    from shared.utils.DeepSeekClient import DeepSeekRedisStreamClient
    ai_client = DeepSeekRedisStreamClient(redis_service)
    logger.debug("[Celery Worker Async] DeepSeek客户端初始化完成")
    
    # 设置对话ID
    if not conversation_id:
        conversation_id = f"ai_query_{user_id}_{int(time.time())}"
    logger.info(f"[Celery Worker Async] 会话ID: {conversation_id}")
    
    # 执行AI查询
    try:
        logger.debug(f'[Celery Worker Async] 提示词长度: {len(str(prompt))} 字符')
        logger.debug(f'[Celery Worker Async] 温度参数: {temperature}')
        
        # 通过消息通知状态更新（如果需要状态机管理，由API服务处理）
        # 注意：这里使用 user_id 作为 job_id，因为这是AI查询任务
        await message_publisher.publish_status_update(
            job_id=context.user_id,
            status=JobStatus.RUNNING.value,
            trigger="ai_query_start",
            operator_type="system"
        )
        
        logger.info("[Celery Worker Async] 🤖 开始调用AI客户端...")
        import time as time_module
        start_time = time_module.time()
        result = await ai_client.chat_completion(
            messages=prompt,
            temperature=temperature,
            conversation_id=conversation_id,
        )
        elapsed = time_module.time() - start_time
        logger.info(f"✅ [Celery Worker Async] AI客户端调用完成，总耗时: {elapsed:.2f}秒")
        logger.debug(f'[Celery Worker Async] 结果长度: {len(str(result))} 字符')
        
        # 保存结果
        logger.debug("[Celery Worker Async] 保存结果到Redis...")
        await task_service.save_task_result(context.user_id, {
            'result': result,
            'conversation_id': conversation_id,
            'timestamp': time.time()
        })
        logger.debug("[Celery Worker Async] 结果已保存")
        
        logger.debug("[Celery Worker Async] 设置任务状态为完成...")
        await task_service.set_task_status(context.user_id, "complete")
        
        # 通知任务完成
        await message_publisher.publish_status_update(
            job_id=context.user_id,
            status=JobStatus.DONE.value,
            trigger="ai_query_complete",
            operator_type="system",
        )
        
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        logger.error(f"❌ [Celery Worker Async] 异步处理失败: {e}")
        await task_service.mark_task_failed(context.user_id, str(e))
        
        # 通知任务失败
        await message_publisher.publish_status_update(
            job_id=context.user_id,
            status=JobStatus.FAILED.value,
            trigger="ai_query_failed",
            operator_type="system",
            metadata={"error": str(e)},
        )
        raise




