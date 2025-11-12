"""
Webhook处理服务（API服务专用）
处理Job完成和失败的Webhook发送

使用混合重试机制：
- 第一次尝试同步发送（快速成功）
- 失败后创建Celery任务进行异步重试（不阻塞主流程）
"""
from datetime import datetime
from typing import Any, Dict, Optional

from app.repositories.webhook_repository import WebhookRepository
from shared.services.storage.file_upload_service import FileUploadService
from loguru import logger


class WebhookHandlerService:
    """Webhook处理服务"""
    
    def __init__(self):
        self.webhook_repo = WebhookRepository()
        self.upload_service = FileUploadService()
    
    async def handle_job_completion_webhook(
        self,
        db,
        job_id: str,
        job_result: Any,
        webhook_url: str
    ) -> Dict[str, Any]:
        """
        处理Job完成的Webhook发送
        
        Args:
            db: 数据库会话
            job_id: 任务ID
            job_result: JobResult对象
            webhook_url: Webhook URL
        
        Returns:
            Dict: 发送结果
        """
        try:
            # 构建Webhook payload
            webhook_payload: Dict[str, Any] = {
                "event": "job.completed",
                "job_id": job_id,
                "status": "completed",
                "delivery_mode": "url",
                "completed_at": datetime.utcnow().isoformat()
            }
            
            # 添加 result_url（ZIP 包下载链接）
            if job_result and job_result.result_s3_key:
                result_url_info = await self.upload_service.generate_download_url(job_result.result_s3_key)
                webhook_payload["result_url"] = result_url_info["download_url"]
            
            # 添加 result（包含 checksum 和 statistics）
            if job_result and job_result.inline_payload:
                webhook_payload["result"] = job_result.inline_payload
            
            # 发送Webhook（混合重试机制：第一次同步，失败后异步重试）
            from app.services.webhook.webhook_service import WebhookService
            
            webhook_service = WebhookService()
            
            # 第一次尝试同步发送（快速成功）
            first_result = await webhook_service.send_webhook(
                job_id=job_id,
                webhook_url=webhook_url,
                payload=webhook_payload,
                attempt_number=1
            )
            
            if first_result.get("success", False):
                logger.info(f"Job完成Webhook发送成功: job_id={job_id}, attempt=1")
                return first_result
            
            # 第一次失败，创建Celery任务进行异步重试
            logger.info(f"Job完成Webhook第一次尝试失败，创建异步重试任务: job_id={job_id}")
            from shared.core.celery_app import get_celery_app
            celery_app = get_celery_app()
            
            retry_task = celery_app.signature(
                'app.core.tasks.webhook_tasks.send_webhook_retry_task',
                args=[job_id, webhook_url, webhook_payload, 2]
            )
            retry_task.apply_async()
            
            logger.info(f"Job完成Webhook异步重试任务已创建: job_id={job_id}")
            return first_result  # 返回第一次尝试的结果
            
        except Exception as e:
            logger.error(f"处理Job完成Webhook失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_job_failure_webhook(
        self,
        db,
        job_id: str,
        error_message: str,
        error_type: Optional[str] = None,
        webhook_url: str = None
    ) -> Dict[str, Any]:
        """
        处理Job失败的Webhook发送
        
        Args:
            db: 数据库会话
            job_id: 任务ID
            error_message: 错误消息
            error_type: 错误类型（可选）
            webhook_url: Webhook URL（可选，如果为None则从Job中获取）
        
        Returns:
            Dict: 发送结果
        """
        try:
            # 如果未提供webhook_url，从Job中获取
            if not webhook_url:
                from app.repositories.job_repository import JobRepository
                job_repo = JobRepository()
                job = await job_repo.get_job_by_id(db, job_id)
                if not job or not job.webhook_enabled or not job.webhook_url:
                    logger.info(f"Job {job_id} Webhook未启用，跳过")
                    return {"success": False, "skipped": True, "reason": "webhook_not_enabled"}
                webhook_url = job.webhook_url
            
            # 构建Webhook payload
            webhook_payload: Dict[str, Any] = {
                "event": "job.failed",
                "job_id": job_id,
                "status": "failed",
                "failed_at": datetime.utcnow().isoformat(),
                "error": {
                    "message": error_message,
                    "type": error_type or "PROCESSING_ERROR",
                    "code": "PROCESSING_ERROR"
                }
            }
            
            # 发送Webhook（混合重试机制：第一次同步，失败后异步重试）
            from app.services.webhook.webhook_service import WebhookService
            
            webhook_service = WebhookService()
            
            # 第一次尝试同步发送（快速成功）
            first_result = await webhook_service.send_webhook(
                job_id=job_id,
                webhook_url=webhook_url,
                payload=webhook_payload,
                attempt_number=1
            )
            
            if first_result.get("success", False):
                logger.info(f"Job失败Webhook发送成功: job_id={job_id}, attempt=1")
                return first_result
            
            # 第一次失败，创建Celery任务进行异步重试
            logger.info(f"Job失败Webhook第一次尝试失败，创建异步重试任务: job_id={job_id}")
            from shared.core.celery_app import get_celery_app
            celery_app = get_celery_app()
            
            retry_task = celery_app.signature(
                'app.core.tasks.webhook_tasks.send_webhook_retry_task',
                args=[job_id, webhook_url, webhook_payload, 2]
            )
            retry_task.apply_async()
            
            logger.info(f"Job失败Webhook异步重试任务已创建: job_id={job_id}")
            return first_result  # 返回第一次尝试的结果
            
        except Exception as e:
            logger.error(f"处理Job失败Webhook失败: {e}")
            return {"success": False, "error": str(e)}

