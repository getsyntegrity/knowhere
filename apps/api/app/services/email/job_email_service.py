"""
Job邮件服务（API服务专用）
处理Job完成和失败的邮件发送
"""
from typing import Any, Optional

from shared.services.storage.file_upload_service import FileUploadService
from loguru import logger

from .email_service import EmailService
from .models import EmailSendResult


class JobEmailService:
    """Job邮件服务"""
    
    def __init__(self):
        """初始化Job邮件服务"""
        self.upload_service = FileUploadService()
        self.email_service = EmailService()
    
    async def send_job_completion_email(
        self,
        db,
        job_id: str,
        job_result: Any,
        user_email: str,
        user_name: Optional[str] = None,
        job_type: str = "kb_management"
    ) -> EmailSendResult:
        """
        发送Job完成邮件
        
        Args:
            db: 数据库会话
            job_id: 任务ID
            job_result: JobResult对象
            user_email: 用户邮箱
            user_name: 用户名称（可选）
            job_type: 任务类型
        
        Returns:
            邮件发送结果
        """
        try:
            # 生成下载链接（如果有结果文件）
            download_url = None
            if job_result and hasattr(job_result, 'result_s3_key') and job_result.result_s3_key:
                result_url_info = await self.upload_service.generate_download_url(job_result.result_s3_key)
                download_url = result_url_info.get("download_url")
            
            # 获取用户ID（如果有）
            user_id = None
            if db:
                from shared.models.database.job import Job
                from sqlalchemy import select
                try:
                    job_result = await db.execute(select(Job).where(Job.job_id == job_id))
                    job = job_result.scalar_one_or_none()
                    if job and job.user_id:
                        user_id = str(job.user_id)
                except Exception:
                    pass
            
            # 发送邮件
            result = await self.email_service.send_job_completion_email(
                user_email=user_email,
                job_type=job_type,
                job_id=job_id,
                download_url=download_url,
                user_name=user_name or user_email,
                db=db,
                user_id=user_id
            )
            
            logger.info(f"Job完成邮件发送完成: job_id={job_id}, user_email={user_email}, success={result.success}")
            return result
            
        except Exception as e:
            logger.error(f"发送Job完成邮件失败: {e}")
            return EmailSendResult(
                success=False,
                error=str(e)
            )
    
    async def send_job_failure_email(
        self,
        db,
        job_id: str,
        user_email: str,
        error_message: str,
        user_name: Optional[str] = None,
        job_type: str = "kb_management"
    ) -> EmailSendResult:
        """
        发送Job失败邮件
        
        Args:
            db: 数据库会话
            job_id: 任务ID
            user_email: 用户邮箱
            error_message: 错误消息
            user_name: 用户名称（可选）
            job_type: 任务类型
        
        Returns:
            邮件发送结果
        """
        try:
            # 获取用户ID（如果有）
            user_id = None
            if db:
                from shared.models.database.job import Job
                from sqlalchemy import select
                try:
                    job_result = await db.execute(select(Job).where(Job.job_id == job_id))
                    job = job_result.scalar_one_or_none()
                    if job and job.user_id:
                        user_id = str(job.user_id)
                except Exception:
                    pass
            
            # 发送邮件
            result = await self.email_service.send_job_failure_email(
                user_email=user_email,
                job_type=job_type,
                job_id=job_id,
                error_message=error_message,
                user_name=user_name or user_email,
                db=db,
                user_id=user_id
            )
            
            logger.info(f"Job失败邮件发送完成: job_id={job_id}, user_email={user_email}, success={result.success}")
            return result
            
        except Exception as e:
            logger.error(f"发送Job失败邮件失败: {e}")
            return EmailSendResult(
                success=False,
                error=str(e)
            )
