"""
邮件服务
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import resend
from resend import Emails
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.config import settings
from loguru import logger

from .models import (
    EmailMessage,
    EmailRecipient,
    EmailSendResult,
    BatchEmailRequest,
    BatchEmailResult,
)
from .utils import EmailRetryHandler, EmailValidator


class EmailService:
    """邮件服务"""
    
    def __init__(self):
        """初始化邮件服务"""
        self.resend_api_key = settings.RESEND_API_KEY
        self.from_email = settings.RESEND_FROM_EMAIL
        self.from_name = settings.RESEND_FROM_NAME
        self.max_retries = settings.RESEND_MAX_RETRIES
        self.retry_delay = settings.RESEND_RETRY_DELAY
        
        # Resend模板ID配置
        self.template_ids = {
            "welcome": settings.RESEND_TEMPLATE_WELCOME,
            "purchase_confirmation": settings.RESEND_TEMPLATE_PURCHASE_CONFIRMATION,
            "job_completion": settings.RESEND_TEMPLATE_JOB_COMPLETION,
            "job_failure": settings.RESEND_TEMPLATE_JOB_FAILURE,
        }
        
        # Resend模板开关配置
        self.template_enabled = {
            "welcome": settings.RESEND_TEMPLATE_WELCOME_ENABLED,
            "purchase_confirmation": settings.RESEND_TEMPLATE_PURCHASE_CONFIRMATION_ENABLED,
            "job_completion": settings.RESEND_TEMPLATE_JOB_COMPLETION_ENABLED,
            "job_failure": settings.RESEND_TEMPLATE_JOB_FAILURE_ENABLED,
        }
        
        # 初始化 Resend 客户端
        if self.resend_api_key:
            resend.api_key = self.resend_api_key
            self.resend_emails = Emails()
        else:
            self.resend_emails = None
            logger.warning("Resend API Key未配置，邮件发送功能将不可用")
        
        # 初始化重试处理器
        self.retry_handler = EmailRetryHandler(
            max_retries=self.max_retries,
            retry_delay=self.retry_delay
        )
        
        # 初始化邮箱验证器
        self.email_validator = EmailValidator()
    
    async def send_email(
        self, 
        message: EmailMessage,
        db: Optional[AsyncSession] = None
    ) -> EmailSendResult:
        """
        发送邮件
        
        Args:
            message: 邮件消息模型
            db: 数据库会话（可选，用于记录日志）
            
        Returns:
            邮件发送结果
        """
        if not self.resend_emails:
            result = EmailSendResult(
                success=False,
                error="Resend API Key未配置"
            )
            # 记录日志
            if db:
                await self._log_email(db, message, result)
            return result
        
        # 验证邮箱地址
        for recipient in message.to:
            if not self.email_validator.validate(recipient.email):
                result = EmailSendResult(
                    success=False,
                    error=f"无效的邮箱地址: {recipient.email}"
                )
                # 记录日志
                if db:
                    await self._log_email(db, message, result)
                return result
        
        # 构建发件人信息
        from_email = message.from_email or self.from_email
        from_name = message.from_name or self.from_name
        from_address = f"{from_name} <{from_email}>"
        
        # 构建收件人列表
        to_addresses = [r.email for r in message.to]
        
        try:
            # 使用重试机制发送邮件
            result = await self.retry_handler.execute_with_retry(
                self._send_email_internal,
                from_address=from_address,
                to_addresses=to_addresses,
                subject=message.subject,
                html_content=message.html_content,
                text_content=message.text_content,
                reply_to=message.reply_to,
                cc=message.cc,
                bcc=message.bcc,
                tags=message.tags,
                template_id=message.template_id,
                template_variables=message.template_variables,
            )
            
            # Resend SDK 返回的是 SendResponse 对象（TypedDict），可以像字典一样访问
            message_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
            logger.info(f"邮件发送成功: {to_addresses}, message_id: {message_id}")
            send_result = EmailSendResult(
                success=True,
                message_id=message_id
            )
            
            # 记录日志
            if db:
                await self._log_email(db, message, send_result)
            
            return send_result
            
        except Exception as e:
            logger.error(f"邮件发送失败: {to_addresses}, 错误: {str(e)}")
            send_result = EmailSendResult(
                success=False,
                error=str(e)
            )
            
            # 记录日志
            if db:
                await self._log_email(db, message, send_result)
            
            return send_result
    
    async def _send_email_internal(
        self,
        from_address: str,
        to_addresses: List[str],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        reply_to: Optional[List[str]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        template_id: Optional[str] = None,
        template_variables: Optional[dict] = None,
    ) -> dict:
        """
        内部方法：实际发送邮件
        
        Args:
            from_address: 发件人地址
            to_addresses: 收件人地址列表
            subject: 邮件主题
            html_content: HTML内容
            text_content: 纯文本内容
            reply_to: 回复地址列表
            cc: 抄送列表
            bcc: 密送列表
            tags: 标签列表
            
        Returns:
            Resend API 响应结果
        """
        params = {
            "from": from_address,
            "to": to_addresses,
        }
        
        # 如果使用模板，则使用模板ID和变量
        if template_id:
            from resend.emails._emails import EmailTemplate
            template_config = {"id": template_id}
            if template_variables:
                template_config["variables"] = template_variables
            params["template"] = EmailTemplate(template_config)
            # 使用模板时，subject 是可选的（可以在模板中定义）
            if subject:
                params["subject"] = subject
        else:
            # 不使用模板时，需要提供 subject 和内容
            params["subject"] = subject
            if html_content:
                params["html"] = html_content
            if text_content:
                params["text"] = text_content
        
        if reply_to:
            params["reply_to"] = reply_to
        if cc:
            params["cc"] = cc
        if bcc:
            params["bcc"] = bcc
        if tags:
            params["tags"] = tags
        
        # 注意：Resend SDK 的 send 方法是同步的，需要在线程池中执行
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.resend_emails.send(params)
        )
        
        return result
    
    async def _log_email(
        self,
        db: AsyncSession,
        message: EmailMessage,
        result: EmailSendResult
    ) -> None:
        """
        记录邮件发送日志
        
        Args:
            db: 数据库会话
            message: 邮件消息
            result: 发送结果
        """
        try:
            from shared.models.database.email_log import EmailLog
            
            # 获取第一个收件人信息
            recipient = message.to[0] if message.to else None
            if not recipient:
                return
            
            # 转换 user_id
            user_id = None
            if message.user_id:
                try:
                    user_id = UUID(message.user_id) if isinstance(message.user_id, str) else message.user_id
                except (ValueError, AttributeError):
                    pass
            
            # 创建日志记录
            email_log = EmailLog(
                user_id=user_id,
                email_type=message.email_type or "custom",
                recipient_email=recipient.email,
                recipient_name=recipient.name,
                subject=message.subject,
                template_id=message.template_id,
                template_variables=message.template_variables,
                success=result.success,
                message_id=result.message_id,
                error_message=result.error,
                job_id=message.job_id,
            )
            
            db.add(email_log)
            await db.commit()
            
        except Exception as e:
            logger.error(f"记录邮件发送日志失败: {e}")
            # 不抛出异常，避免影响邮件发送流程
            try:
                await db.rollback()
            except Exception:
                pass
    
    async def send_batch_email(
        self, 
        request: BatchEmailRequest,
        db: Optional[AsyncSession] = None
    ) -> BatchEmailResult:
        """
        批量发送邮件
        
        Args:
            request: 批量邮件请求
            
        Returns:
            批量发送结果
        """
        results = []
        success_count = 0
        failed_count = 0
        
        for message in request.messages:
            result = await self.send_email(message, db=db)
            results.append(result)
            
            if result.success:
                success_count += 1
            else:
                failed_count += 1
        
        return BatchEmailResult(
            total=len(request.messages),
            success=success_count,
            failed=failed_count,
            results=results
        )
    
    async def send_welcome_email(
        self,
        user_email: str,
        user_name: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None
    ) -> EmailSendResult:
        """
        发送欢迎邮件
        
        Args:
            user_email: 用户邮箱
            user_name: 用户名称（可选）
            
        Returns:
            邮件发送结果
        """
        try:
            user_name = user_name or user_email
            template_id = self.template_ids.get("welcome")
            template_enabled = self.template_enabled.get("welcome", True)
            
            # 检查模板是否启用
            if not template_enabled:
                return EmailSendResult(
                    success=False,
                    error="欢迎邮件模板未启用"
                )
            
            # 检查模板ID是否配置
            if not template_id:
                return EmailSendResult(
                    success=False,
                    error="欢迎邮件模板ID未配置，请在Resend控制台创建模板并配置RESEND_TEMPLATE_WELCOME"
                )
            
            # 使用 Resend 模板
            message = EmailMessage(
                to=[EmailRecipient(email=user_email, name=user_name)],
                subject="欢迎使用 Knowhere AI！",
                template_id=template_id,
                template_variables={"user_name": user_name},
                email_type="welcome",
                user_id=user_id,
            )
            
            return await self.send_email(message, db=db)
            
        except Exception as e:
            logger.error(f"发送欢迎邮件失败: {e}")
            return EmailSendResult(
                success=False,
                error=str(e)
            )
    
    async def send_purchase_confirmation_email(
        self,
        user_email: str,
        plan_type: str,
        amount: float,
        user_name: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None
    ) -> EmailSendResult:
        """
        发送购买确认邮件
        
        Args:
            user_email: 用户邮箱
            plan_type: 订阅计划类型
            amount: 金额
            user_name: 用户名称（可选）
            
        Returns:
            邮件发送结果
        """
        try:
            user_name = user_name or user_email
            purchase_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            template_id = self.template_ids.get("purchase_confirmation")
            template_enabled = self.template_enabled.get("purchase_confirmation", True)
            
            # 检查模板是否启用
            if not template_enabled:
                return EmailSendResult(
                    success=False,
                    error="购买确认邮件模板未启用"
                )
            
            # 检查模板ID是否配置
            if not template_id:
                return EmailSendResult(
                    success=False,
                    error="购买确认邮件模板ID未配置，请在Resend控制台创建模板并配置RESEND_TEMPLATE_PURCHASE_CONFIRMATION"
                )
            
            # 使用 Resend 模板
            message = EmailMessage(
                to=[EmailRecipient(email=user_email, name=user_name)],
                subject=f"购买确认 - {plan_type.title()} 订阅",
                template_id=template_id,
                template_variables={
                    "user_name": user_name,
                    "plan_type": plan_type,
                    "amount": amount,
                    "purchase_time": purchase_time,
                },
                email_type="purchase_confirmation",
                user_id=user_id,
            )
            
            return await self.send_email(message, db=db)
            
        except Exception as e:
            logger.error(f"发送购买确认邮件失败: {e}")
            return EmailSendResult(
                success=False,
                error=str(e)
            )
    
    async def send_job_completion_email(
        self,
        user_email: str,
        job_type: str,
        job_id: str,
        download_url: Optional[str] = None,
        user_name: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None
    ) -> EmailSendResult:
        """
        发送任务完成邮件
        
        Args:
            user_email: 用户邮箱
            job_type: 任务类型
            job_id: 任务ID
            download_url: 下载链接（可选）
            user_name: 用户名称（可选）
            
        Returns:
            邮件发送结果
        """
        try:
            user_name = user_name or user_email
            job_type_display = job_type.replace('_', ' ').title()
            completion_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            template_id = self.template_ids.get("job_completion")
            template_enabled = self.template_enabled.get("job_completion", True)
            
            # 检查模板是否启用
            if not template_enabled:
                return EmailSendResult(
                    success=False,
                    error="任务完成邮件模板未启用"
                )
            
            # 检查模板ID是否配置
            if not template_id:
                return EmailSendResult(
                    success=False,
                    error="任务完成邮件模板ID未配置，请在Resend控制台创建模板并配置RESEND_TEMPLATE_JOB_COMPLETION"
                )
            
            # 使用 Resend 模板
            message = EmailMessage(
                to=[EmailRecipient(email=user_email, name=user_name)],
                subject=f"任务完成 - {job_type_display}",
                template_id=template_id,
                template_variables={
                    "user_name": user_name,
                    "job_type_display": job_type_display,
                    "job_id": job_id,
                    "completion_time": completion_time,
                    "download_url": download_url or "",
                },
                email_type="job_completion",
                user_id=user_id,
                job_id=job_id,
            )
            
            return await self.send_email(message, db=db)
            
        except Exception as e:
            logger.error(f"发送任务完成邮件失败: {e}")
            return EmailSendResult(
                success=False,
                error=str(e)
            )
    
    async def send_job_failure_email(
        self,
        user_email: str,
        job_type: str,
        job_id: str,
        error_message: str,
        user_name: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None
    ) -> EmailSendResult:
        """
        发送任务失败邮件
        
        Args:
            user_email: 用户邮箱
            job_type: 任务类型
            job_id: 任务ID
            error_message: 错误消息
            user_name: 用户名称（可选）
            
        Returns:
            邮件发送结果
        """
        try:
            user_name = user_name or user_email
            job_type_display = job_type.replace('_', ' ').title()
            failure_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            template_id = self.template_ids.get("job_failure")
            template_enabled = self.template_enabled.get("job_failure", True)
            
            # 检查模板是否启用
            if not template_enabled:
                return EmailSendResult(
                    success=False,
                    error="任务失败邮件模板未启用"
                )
            
            # 检查模板ID是否配置
            if not template_id:
                return EmailSendResult(
                    success=False,
                    error="任务失败邮件模板ID未配置，请在Resend控制台创建模板并配置RESEND_TEMPLATE_JOB_FAILURE"
                )
            
            # 使用 Resend 模板
            message = EmailMessage(
                to=[EmailRecipient(email=user_email, name=user_name)],
                subject=f"任务失败 - {job_type_display}",
                template_id=template_id,
                template_variables={
                    "user_name": user_name,
                    "job_type_display": job_type_display,
                    "job_id": job_id,
                    "failure_time": failure_time,
                    "error_message": error_message,
                },
                email_type="job_failure",
                user_id=user_id,
                job_id=job_id,
            )
            
            return await self.send_email(message, db=db)
            
        except Exception as e:
            logger.error(f"发送任务失败邮件失败: {e}")
            return EmailSendResult(
                success=False,
                error=str(e)
            )
