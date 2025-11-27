"""
邮件服务模块
"""
from .email_service import EmailService
from .models import (
    EmailMessage,
    EmailRecipient,
    EmailSendResult,
    BatchEmailRequest,
    BatchEmailResult,
)
from .utils import EmailRetryHandler, EmailValidator

__all__ = [
    "EmailService",
    "EmailMessage",
    "EmailRecipient",
    "EmailSendResult",
    "BatchEmailRequest",
    "BatchEmailResult",
    "EmailRetryHandler",
    "EmailValidator",
]

