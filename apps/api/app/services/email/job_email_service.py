"""
Job邮件服务（API服务专用）
处理Job完成和失败的邮件发送
"""
from typing import Any, Dict, Optional

from app.services.storage.file_upload_service import FileUploadService
from loguru import logger


class JobEmailService:
    """Job邮件服务"""
    
    def __init__(self):
        self.upload_service = FileUploadService()
    
    async def send_job_completion_email(
        self,
        db,
        job_id: str,
        job_result: Any,
        user_email: str,
        user_name: Optional[str] = None,
        job_type: str = "kb_management"
    ) -> Dict[str, Any]:
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
            Dict: 发送结果
        """
        try:
            # 生成下载链接（如果有结果文件）
            download_url = None
            if job_result and job_result.result_s3_key:
                result_url_info = await self.upload_service.generate_download_url(job_result.result_s3_key)
                download_url = result_url_info.get("download_url")
            
            # 发送邮件
            from app.services.email.email_service import EmailService
            email_service = EmailService()
            
            result = await email_service.send_job_completion_email(
                user_email=user_email,
                job_type=job_type,
                job_id=job_id,
                download_url=download_url,
                user_name=user_name or user_email
            )
            
            logger.info(f"Job完成邮件发送完成: job_id={job_id}, user_email={user_email}, result={result}")
            return result
            
        except Exception as e:
            logger.error(f"发送Job完成邮件失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_job_failure_email(
        self,
        db,
        job_id: str,
        user_email: str,
        error_message: str,
        user_name: Optional[str] = None,
        job_type: str = "kb_management"
    ) -> Dict[str, Any]:
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
            Dict: 发送结果
        """
        try:
            # 构建邮件内容
            from app.services.email.email_service import EmailService
            email_service = EmailService()
            
            subject = f"任务失败 - {job_type.replace('_', ' ').title()}"
            html_content = self._get_job_failure_html(
                user_name or user_email, job_type, job_id, error_message
            )
            text_content = self._get_job_failure_text(
                user_name or user_email, job_type, job_id, error_message
            )
            
            result = await email_service.send_email(
                to=user_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
            logger.info(f"Job失败邮件发送完成: job_id={job_id}, user_email={user_email}, result={result}")
            return result
            
        except Exception as e:
            logger.error(f"发送Job失败邮件失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_job_failure_html(self, user_name: str, job_type: str, job_id: str, error_message: str) -> str:
        """获取任务失败邮件HTML模板"""
        from datetime import datetime
        job_type_display = job_type.replace('_', ' ').title()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>任务失败</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #dc3545; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .job-info {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .error-box {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚠️ 任务失败</h1>
                </div>
                <div class="content">
                    <h2>你好，{user_name}！</h2>
                    <p>很抱歉，您的 {job_type_display} 任务处理失败。</p>
                    
                    <div class="job-info">
                        <h3>任务详情</h3>
                        <p><strong>任务类型：</strong> {job_type_display}</p>
                        <p><strong>任务ID：</strong> {job_id}</p>
                        <p><strong>失败时间：</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                    
                    <div class="error-box">
                        <h3>错误信息</h3>
                        <p>{error_message}</p>
                    </div>
                    
                    <p>如有任何问题，请随时联系我们的支持团队。</p>
                </div>
                <div class="footer">
                    <p>© 2024 Knowhere AI. 保留所有权利。</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_job_failure_text(self, user_name: str, job_type: str, job_id: str, error_message: str) -> str:
        """获取任务失败邮件纯文本模板"""
        from datetime import datetime
        job_type_display = job_type.replace('_', ' ').title()
        
        return f"""
        任务失败
        
        你好，{user_name}！
        
        很抱歉，您的 {job_type_display} 任务处理失败。
        
        任务详情：
        - 任务类型：{job_type_display}
        - 任务ID：{job_id}
        - 失败时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        错误信息：
        {error_message}
        
        如有任何问题，请随时联系我们的支持团队。
        
        © 2024 Knowhere AI. 保留所有权利。
        """

