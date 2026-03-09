"""
Celery任务定义
迁移自ARQ任务，支持优先级和队列路由
"""

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.services.messaging.sync_publisher import (
    close_sync_message_publisher,
)

# 获取Celery应用
celery_app = get_celery_app()

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
