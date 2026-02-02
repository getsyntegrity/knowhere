"""
邮件数据模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailRecipient(BaseModel):
    """邮件收件人"""
    email: EmailStr
    name: Optional[str] = None


class EmailAttachment(BaseModel):
    """邮件附件"""
    filename: str
    content: bytes
    content_type: Optional[str] = None


class EmailMessage(BaseModel):
    """邮件消息模型"""
    to: List[EmailRecipient] = Field(..., description="收件人列表")
    subject: str = Field(..., description="邮件主题")
    html_content: Optional[str] = Field(None, description="HTML内容")
    text_content: Optional[str] = Field(None, description="纯文本内容")
    from_email: Optional[EmailStr] = Field(None, description="发件人邮箱（覆盖默认值）")
    from_name: Optional[str] = Field(None, description="发件人名称（覆盖默认值）")
    reply_to: Optional[List[EmailStr]] = Field(None, description="回复地址列表")
    cc: Optional[List[EmailStr]] = Field(None, description="抄送列表")
    bcc: Optional[List[EmailStr]] = Field(None, description="密送列表")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    attachments: Optional[List[EmailAttachment]] = Field(None, description="附件列表")
    template_id: Optional[str] = Field(None, description="Resend模板ID")
    template_variables: Optional[Dict[str, Any]] = Field(None, description="模板变量（用于Resend模板）")
    # 日志记录相关字段
    email_type: Optional[str] = Field(None, description="邮件类型（用于日志记录）")
    user_id: Optional[str] = Field(None, description="用户ID（用于日志记录）")
    job_id: Optional[str] = Field(None, description="任务ID（用于日志记录）")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "to": [{"email": "user@example.com", "name": "User Name"}],
                "subject": "测试邮件",
                "html_content": "<h1>Hello</h1>",
                "text_content": "Hello",
            }
        }
    )


class EmailSendResult(BaseModel):
    """邮件发送结果"""
    success: bool = Field(..., description="是否成功")
    message_id: Optional[str] = Field(None, description="邮件ID")
    error: Optional[str] = Field(None, description="错误信息")


class BatchEmailRequest(BaseModel):
    """批量邮件请求"""
    messages: List[EmailMessage] = Field(..., description="邮件消息列表")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "messages": [
                    {
                        "to": [{"email": "user1@example.com"}],
                        "subject": "邮件1",
                        "html_content": "<p>内容1</p>",
                    },
                    {
                        "to": [{"email": "user2@example.com"}],
                        "subject": "邮件2",
                        "html_content": "<p>内容2</p>",
                    },
                ]
            }
        }
    )


class BatchEmailResult(BaseModel):
    """批量邮件发送结果"""
    total: int = Field(..., description="总数")
    success: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    results: List[EmailSendResult] = Field(..., description="详细结果列表")

