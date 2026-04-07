"""Exceptions module for shared exception classes."""

from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.core.exceptions.domain_exceptions import (
    ValidationException,
    AuthException,
    PermissionDeniedException,
    NotFoundException,
    ConflictException,
    RateLimitException,
    QuotaExceededException,
    UnavailableException,
    TimeoutException,
    UnknownException,
    FileSystemException,
    LibreOfficeServiceException,
)
from shared.core.exceptions.retryable_exceptions import RETRYABLE_EXCEPTIONS
from shared.core.exceptions.webhook_exceptions import (
    WebhookException,
    WebhookConfigException,
    WebhookDeliveryException,
)

__all__ = [
    # Base (do not raise directly)
    "KnowhereException",
    # Client Errors (4xx)
    "ValidationException",
    "AuthException",
    "PermissionDeniedException",
    "NotFoundException",
    "ConflictException",
    "RateLimitException",
    "QuotaExceededException",
    # Server Errors (5xx)
    "UnavailableException",
    "TimeoutException",
    "UnknownException",
    "FileSystemException",
    "LibreOfficeServiceException",
    # Webhook Exceptions
    "WebhookException",
    "WebhookConfigException",
    "WebhookDeliveryException",
    # Celery retry config
    "RETRYABLE_EXCEPTIONS",
]
