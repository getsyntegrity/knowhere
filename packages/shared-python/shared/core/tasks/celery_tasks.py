"""
Celery任务定义
迁移自ARQ任务，支持优先级和队列路由
"""
import time

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.celery_router import (
    CeleryTaskRouter,
    TaskContext,
)
from shared.services.messaging.sync_publisher import (
    close_sync_message_publisher,
)
from shared.services.ai.ai_query_service_sync import sync_ai_query_service
from shared.services.redis.redis_sync_service import (
    SyncRedisServiceFactory,
    SyncTaskRedisService,
)

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

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Release greenlet-local sync publisher after task lifecycle."""
        try:
            close_sync_message_publisher()
        except Exception:
            pass

@celery_app.task(bind=True, base=BaseTask, name='shared.core.tasks.celery_tasks.process_ai_query')
def process_ai_query(self, prompt: str, user_id: str, temperature: float = 0.1, 
                    conversation_id: str = None, **kwargs):
    """
    AI查询任务 - 高优先级
    """
    logger.info(f"🚀 [Celery Worker] AI查询任务开始: task_id={self.request.id}, user_id={user_id}")
    
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

        result = _process_ai_query_sync(prompt, user_id, temperature, conversation_id, context, **kwargs)
        logger.info(f"✅ [Celery Worker] AI查询任务完成: status={result.get('status')}")
        return result
            
    except Exception as e:
        logger.error(f"❌ [Celery Worker] AI查询任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

def _process_ai_query_sync(
    prompt: str,
    user_id: str,
    temperature: float,
    conversation_id: str,
    context: TaskContext,
    **kwargs,
):
    """同步AI查询处理（gevent worker path）"""
    redis_service = SyncRedisServiceFactory.get_service()
    task_service = SyncTaskRedisService(redis_service)

    task_service.set_task_status(context.user_id, "正在连接AI大模型...")
    if not conversation_id:
        conversation_id = f"ai_query_{user_id}_{int(time.time())}"

    try:
        logger.debug(f"[Celery Worker Sync] 提示词长度: {len(str(prompt))} 字符")
        logger.debug(f"[Celery Worker Sync] 温度参数: {temperature}")

        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = prompt

        result = sync_ai_query_service.query_ai(
            messages=messages,
            user_id=user_id,
            conversation_id=conversation_id,
            temperature=temperature,
            **kwargs,
        )
        task_service.save_task_result(
            context.user_id,
            {
                "result": result,
                "conversation_id": conversation_id,
                "timestamp": time.time(),
            },
        )
        task_service.set_task_status(context.user_id, "complete")

        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"❌ [Celery Worker Sync] 处理失败: {e}")
        task_service.mark_task_failed(context.user_id, str(e))
        raise
