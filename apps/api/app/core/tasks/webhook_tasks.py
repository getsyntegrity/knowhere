"""
Webhook Celery任务
用于异步重试Webhook发送
"""
import asyncio
from typing import Any, Dict

from app.core.celery_app import get_celery_app
from celery import Task
from loguru import logger

# 获取Celery应用
celery_app = get_celery_app()


class WebhookRetryTask(Task):
    """Webhook重试任务基类"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"Webhook重试任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"Webhook重试任务 {task_id} 执行失败: {exc}")
        logger.error(f"异常信息: {einfo}")


@celery_app.task(
    bind=True,
    base=WebhookRetryTask,
    max_retries=4,
    default_retry_delay=60,
    name='app.core.tasks.webhook_tasks.send_webhook_retry_task'
)
def send_webhook_retry_task(
    self,
    job_id: str,
    webhook_url: str,
    payload: Dict[str, Any],
    attempt: int = 2
):
    """
    Webhook异步重试任务（从第2次尝试开始）
    
    Args:
        job_id: 任务ID
        webhook_url: Webhook URL
        payload: Webhook payload
        attempt: 当前尝试次数（从2开始）
    
    Returns:
        Dict: 发送结果
    """
    try:
        from app.services.webhook.webhook_service import WebhookService

        # 创建事件循环（Celery任务在同步上下文中运行）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            webhook_service = WebhookService()
            
            # 执行异步发送
            result = loop.run_until_complete(
                webhook_service.send_webhook(
                    job_id=job_id,
                    webhook_url=webhook_url,
                    payload=payload,
                    attempt_number=attempt
                )
            )
            
            if result.get("success", False):
                logger.info(f"Webhook重试成功: job_id={job_id}, attempt={attempt}")
                return result
            
            # 如果失败且还有重试次数，继续重试
            if attempt < webhook_service.max_retries:
                delay = webhook_service._calculate_delay(attempt)
                logger.info(f"Webhook重试失败，继续重试: job_id={job_id}, attempt={attempt}, next_delay={delay}s")
                raise self.retry(
                    countdown=int(delay),
                    args=[job_id, webhook_url, payload, attempt + 1]
                )
            
            # 所有重试都失败
            logger.error(f"Webhook所有重试都失败: job_id={job_id}, attempts={attempt}")
            return result
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Webhook重试任务异常: job_id={job_id}, attempt={attempt}, error={e}")
        
        # 如果还有重试次数，继续重试
        if attempt < 5:  # max_retries = 5 (1次同步 + 4次异步)
            from app.services.webhook.webhook_service import WebhookService
            webhook_service = WebhookService()
            delay = webhook_service._calculate_delay(attempt)
            raise self.retry(
                exc=e,
                countdown=int(delay),
                args=[job_id, webhook_url, payload, attempt + 1]
            )
        
        # 所有重试都失败
        raise

