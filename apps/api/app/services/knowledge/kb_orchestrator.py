"""
知识库管理编排服务
"""
from typing import Optional

from shared.core.celery_router import task_router
# 注意：任务已迁移到 Worker 服务，通过任务名称字符串引用
from shared.core.exceptions.DomainExceptions import KnowhereException, WorkerHandlingException
from loguru import logger


class KBOrchestrator:
    """知识库编排器"""
    
    def __init__(self):
        self.task_router = task_router
    
    async def start_workflow(
        self,
        db,
        job_id: str,
        source_type: str,
        file_path: Optional[str] = None,
        file_url: Optional[str] = None,
        user_id: str = None
    ) -> str:
        """
        启动知识库管理工作流
        
        Args:
            db: 数据库会话
            job_id: 任务ID
            source_type: 文件来源类型
            file_path: 文件路径（直传时使用）
            file_url: 文件URL（URL外链时使用）
            user_id: 用户ID
            
        Returns:
            str: 工作流ID
        """
        try:
            # 如果source_type是url但没有提供file_url，尝试从job_metadata中获取
            if source_type == "url" and not file_url:
                from shared.models.schemas.job_metadata import JobMetadataHelper
                from app.repositories.job_repository import JobRepository
                from shared.services.redis import RedisServiceFactory
                
                job_repo = JobRepository()
                redis_service = RedisServiceFactory.get_service()
                job_metadata = await job_repo.get_job_metadata(db, job_id, redis_service)
                file_url = JobMetadataHelper.get_field(job_metadata, "file_url")
            
            # 获取队列名称
            queue_name = self.task_router.get_queue_for_job("kb_management", user_id)
            
            # 启动单任务（文件已通过S3直传）
            # 任务包含：解析、向量化、生成ZIP、上传S3、发布结果消息
            # Webhook和邮件发送已迁移到API服务，由消息处理器处理
            from celery import signature
            task_signature = signature(
                'app.core.tasks.kb_tasks.parse_task',
                args=[job_id],
                kwargs={'user_id': user_id, 'job_type': 'kb_management'}
            ).set(queue=queue_name)
            
            # 启动任务
            result = task_signature.apply_async()
            
            logger.info(f"知识库管理任务已启动: job_id={job_id}, task_id={result.id}, queue={queue_name}")
            
            return result.id
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"启动知识库管理工作流失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"启动知识库管理工作流失败: {str(e)}",
                original_exception=e
            )
    
    def create_workflow_chain(self, job_id: str, user_id: str, queue_name: str = None):
        """
        创建知识库管理任务（用于测试或手动执行）
        
        Args:
            job_id: 任务ID
            user_id: 用户ID
            queue_name: 队列名称（可选）
            
        Returns:
            signature: Celery任务签名
        """
        if not queue_name:
            queue_name = self.task_router.get_queue_for_job("kb_management", user_id)
        
        from celery import signature

        # 返回单任务签名（任务包含：解析、向量化、生成ZIP、上传S3、发布结果消息）
        # Webhook和邮件发送已迁移到API服务，由消息处理器处理
        return signature(
            'app.core.tasks.kb_tasks.parse_task',
            args=[job_id],
            kwargs={'user_id': user_id, 'job_type': 'kb_management'}
        ).set(queue=queue_name)
    
    def get_workflow_status(self, workflow_id: str) -> dict:
        """
        获取工作流状态
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            dict: 工作流状态信息
        """
        try:
            from shared.core.celery_app import get_celery_app
            celery_app = get_celery_app()
            
            result = celery_app.AsyncResult(workflow_id)
            
            return {
                "workflow_id": workflow_id,
                "status": result.state,
                "result": result.result if result.state == 'SUCCESS' else None,
                "error": str(result.info) if result.state == 'FAILURE' else None
            }
            
        except Exception as e:
            logger.error(f"获取工作流状态失败: {e}")
            return {
                "workflow_id": workflow_id,
                "status": "UNKNOWN",
                "error": str(e)
            }
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        """
        取消工作流
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            bool: 是否成功取消
        """
        try:
            from shared.core.celery_app import get_celery_app
            celery_app = get_celery_app()
            
            result = celery_app.AsyncResult(workflow_id)
            result.revoke(terminate=True)
            
            logger.info(f"工作流已取消: {workflow_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消工作流失败: {e}")
            return False
