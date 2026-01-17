"""
Redis-related exception definitions
"""
from typing import Optional

from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.core.response.ErrorCode import ErrorCode


class RedisConnectionError(KnowhereException):
    """Redis connection exception"""

    def __init__(
        self,
        internal_message: str,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAVAILABLE,
            internal_message=internal_message,
            user_message=user_message or "Service temporarily unavailable. Please try again later.",
            details={"component": "redis", "error_type": "connection"},
            original_exception=original_exception,
        )


class RedisOperationError(KnowhereException):
    """Redis operation exception"""

    def __init__(
        self,
        internal_message: str,
        operation: Optional[str] = None,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message or "An internal error occurred. Please try again.",
            details={"component": "redis", "error_type": "operation", "operation": operation},
            original_exception=original_exception,
        )


class RedisTimeoutError(KnowhereException):
    """Redis timeout exception"""

    def __init__(
        self,
        internal_message: str,
        timeout_seconds: Optional[float] = None,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.DEADLINE_EXCEEDED,
            internal_message=internal_message,
            user_message=user_message or "Request timed out. Please try again.",
            details={"component": "redis", "error_type": "timeout", "timeout_seconds": timeout_seconds},
            original_exception=original_exception,
        )


class RedisConfigurationError(KnowhereException):
    """Redis configuration exception"""

    def __init__(
        self,
        internal_message: str,
        config_key: Optional[str] = None,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.FAILED_PRECONDITION,
            internal_message=internal_message,
            user_message=user_message or "Service configuration error. Please contact support.",
            details={"component": "redis", "error_type": "configuration", "config_key": config_key},
            original_exception=original_exception,
        )
