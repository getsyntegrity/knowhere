"""
邮件测试API路由
"""
from typing import Optional

from app.core.dependencies import get_current_user, get_db
from app.services.email import EmailService
from app.services.email.models import EmailMessage, EmailRecipient, EmailSendResult
from shared.models.database.user import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

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
    current_user: User = Depends(get_current_user),
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
                user_id=str(current_user.id)
            )
        
        elif request.email_type == "purchase_confirmation":
            if not request.plan_type or request.amount is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="purchase_confirmation类型需要提供plan_type和amount参数"
                )
            result = await email_service.send_purchase_confirmation_email(
                user_email=request.to_email,
                plan_type=request.plan_type,
                amount=request.amount,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=str(current_user.id)
            )
        
        elif request.email_type == "job_completion":
            if not request.job_type or not request.job_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="job_completion类型需要提供job_type和job_id参数"
                )
            result = await email_service.send_job_completion_email(
                user_email=request.to_email,
                job_type=request.job_type,
                job_id=request.job_id,
                download_url=request.download_url,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=str(current_user.id)
            )
        
        elif request.email_type == "job_failure":
            if not request.job_type or not request.job_id or not request.error_message:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="job_failure类型需要提供job_type、job_id和error_message参数"
                )
            result = await email_service.send_job_failure_email(
                user_email=request.to_email,
                job_type=request.job_type,
                job_id=request.job_id,
                error_message=request.error_message,
                user_name=request.user_name or request.to_email,
                db=db,
                user_id=str(current_user.id)
            )
        
        elif request.email_type == "custom":
            if not request.subject or (not request.html_content and not request.text_content):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="custom类型需要提供subject和html_content或text_content参数"
                )
            message = EmailMessage(
                to=[EmailRecipient(email=request.to_email, name=request.user_name)],
                subject=request.subject,
                html_content=request.html_content,
                text_content=request.text_content,
                email_type="custom",
                user_id=str(current_user.id),
            )
            result = await email_service.send_email(message, db=db)
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的邮件类型: {request.email_type}"
            )
        
        return EmailTestResponse(
            success=result.success,
            message_id=result.message_id,
            error=result.error,
            email_type=request.email_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试邮件发送失败: {str(e)}"
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

