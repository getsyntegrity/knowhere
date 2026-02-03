"""
邮件测试API路由
"""
from typing import Optional

from app.core.dependencies import get_current_user_id, get_db
from app.services.email import EmailService
from app.services.email.models import EmailMessage, EmailRecipient, EmailSendResult
# from shared.models.database.user import User
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.domain_exceptions import EmailServiceException, ValidationException

router = APIRouter(tags=["邮件测试"])


class EmailTestRequest(BaseModel):
    """邮件测试请求"""
    to_email: EmailStr = Field(..., description="收件人邮箱")
    email_type: str = Field(
        ...,
        description="邮件类型",
        examples=["welcome", "purchase_confirmation", "job_completion", "job_failure", "custom"]
    )
    # 自定义邮件参数
    subject: Optional[str] = Field(None, description="邮件主题（仅custom类型需要）")
    html_content: Optional[str] = Field(None, description="HTML内容（仅custom类型需要）")
    text_content: Optional[str] = Field(None, description="文本内容（仅custom类型需要）")
    # 模板参数
    user_name: Optional[str] = Field(None, description="用户名称")
    plan_type: Optional[str] = Field(None, description="订阅计划类型（purchase_confirmation需要）")
    amount: Optional[float] = Field(None, description="金额（purchase_confirmation需要）")
    job_type: Optional[str] = Field(None, description="任务类型（job_completion/job_failure需要）")
    job_id: Optional[str] = Field(None, description="任务ID（job_completion/job_failure需要）")
    download_url: Optional[str] = Field(None, description="下载链接（job_completion需要）")
    error_message: Optional[str] = Field(None, description="错误消息（job_failure需要）")


class EmailTestResponse(BaseModel):
    """邮件测试响应"""
    success: bool = Field(..., description="是否成功")
    message_id: Optional[str] = Field(None, description="邮件ID")
    error: Optional[str] = Field(None, description="错误信息")
    email_type: str = Field(..., description="邮件类型")


@router.post("/test", response_model=EmailTestResponse, summary="测试邮件发送")
async def test_email(
    request: EmailTestRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    测试邮件发送功能
    
    支持的邮件类型：
    - welcome: 欢迎邮件
    - purchase_confirmation: 购买确认邮件
    - job_completion: 任务完成邮件
    - job_failure: 任务失败邮件
    - custom: 自定义邮件
    """
    try:
        email_service = EmailService()
        result: EmailSendResult
        
        if request.email_type == "welcome":
            result = await email_service.send_welcome_email(
                user_email=request.to_email,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=user_id
            )
        
        elif request.email_type == "purchase_confirmation":
            if not request.plan_type or request.amount is None:
                raise ValidationException(
                    user_message="purchase_confirmation类型需要提供plan_type和amount参数",
                    violations=[{"field": "plan_type", "description": "Required"}, {"field": "amount", "description": "Required"}]
                )
            result = await email_service.send_purchase_confirmation_email(
                user_email=request.to_email,
                plan_type=request.plan_type,
                amount=request.amount,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=user_id
            )
        
        elif request.email_type == "job_completion":
            if not request.job_type or not request.job_id:
                raise ValidationException(
                    user_message="job_completion类型需要提供job_type和job_id参数",
                    violations=[{"field": "job_type", "description": "Required"}, {"field": "job_id", "description": "Required"}]
                )
            result = await email_service.send_job_completion_email(
                user_email=request.to_email,
                job_type=request.job_type,
                job_id=request.job_id,
                download_url=request.download_url,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=user_id
            )
        
        elif request.email_type == "job_failure":
            if not request.job_type or not request.job_id or not request.error_message:
                raise ValidationException(
                    user_message="job_failure类型需要提供job_type、job_id和error_message参数",
                    violations=[{"field": "job_type", "description": "Required"}, {"field": "job_id", "description": "Required"}, {"field": "error_message", "description": "Required"}]
                )
            result = await email_service.send_job_failure_email(
                user_email=request.to_email,
                job_type=request.job_type,
                job_id=request.job_id,
                error_message=request.error_message,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=user_id
            )
        
        elif request.email_type == "custom":
            if not request.subject or (not request.html_content and not request.text_content):
                raise ValidationException(
                    user_message="custom类型需要提供subject和html_content或text_content参数",
                    violations=[{"field": "subject", "description": "Required"}, {"field": "content", "description": "html_content or text_content required"}]
                )
            message = EmailMessage(
                to=[EmailRecipient(email=request.to_email, name=request.user_name)],
                subject=request.subject,
                html_content=request.html_content,
                text_content=request.text_content,
                email_type="custom",
                user_id=user_id,
            )
            result = await email_service.send_email(message, db=db)
        
        else:
            raise ValidationException(
                user_message=f"不支持的邮件类型: {request.email_type}",
                violations=[{"field": "email_type", "description": "Unsupported type"}]
            )
        
        return EmailTestResponse(
            success=result.success,
            message_id=result.message_id,
            error=result.error,
            email_type=request.email_type
        )
        
    except ValidationException:
        raise
    except Exception as e:
        raise EmailServiceException(
            internal_message=f"测试邮件发送失败: {str(e)}"
        )


@router.get("/test/types", summary="获取支持的邮件类型")
async def get_email_types():
    """获取支持的邮件类型列表"""
    return {
        "types": [
            {
                "type": "welcome",
                "name": "欢迎邮件",
                "description": "新用户注册欢迎邮件",
                "required_params": [],
                "optional_params": ["user_name"]
            },
            {
                "type": "purchase_confirmation",
                "name": "购买确认邮件",
                "description": "订阅购买确认邮件",
                "required_params": ["plan_type", "amount"],
                "optional_params": ["user_name"]
            },
            {
                "type": "job_completion",
                "name": "任务完成邮件",
                "description": "任务完成通知邮件",
                "required_params": ["job_type", "job_id"],
                "optional_params": ["user_name", "download_url"]
            },
            {
                "type": "job_failure",
                "name": "任务失败邮件",
                "description": "任务失败通知邮件",
                "required_params": ["job_type", "job_id", "error_message"],
                "optional_params": ["user_name"]
            },
            {
                "type": "custom",
                "name": "自定义邮件",
                "description": "发送自定义内容的邮件",
                "required_params": ["subject", "html_content或text_content"],
                "optional_params": ["user_name"]
            }
        ]
    }

