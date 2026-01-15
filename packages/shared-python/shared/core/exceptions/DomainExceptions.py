"""
Domain-specific exceptions with typed details schemas.

Each exception has a fixed `details` structure that clients can rely on.
Do NOT raise KnowhereException directly - use these domain exceptions.

Usage:
    from shared.core.exceptions import (
        ValidationException,
        RateLimitException,
        NotFoundException,
    )

    # Validation error with violations
    raise ValidationException(
        message="Invalid user input",
        violations=[
            {"field": "email", "description": "Must be a valid email address"},
            {"field": "age", "description": "Must be >= 18"},
        ]
    )

    # Rate limit with retry_after
    raise RateLimitException(retry_after=15)
"""

from typing import Any, Dict, List, Optional, TypedDict

from shared.core.exceptions.KnowhereException import KnowhereException
from shared.core.response.ErrorCode import ErrorCode, SubCode


# ============================================================================
# Type Definitions for Details Schemas
# ============================================================================


class Violation(TypedDict):
    """Schema for validation violations."""

    field: str
    description: str


class ResourceInfo(TypedDict):
    """Schema for resource identification."""

    resource: str
    id: str


# ============================================================================
# Client Error Exceptions (4xx)
# ============================================================================


class ValidationException(KnowhereException):
    """
    Invalid input from client. HTTP 400.

    Details schema:
        {"violations": [{"field": "...", "description": "..."}]}
    """

    def __init__(
        self,
        message: str,
        violations: List[Violation],
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            message=message,
            details={"violations": violations},
            internal_message=internal_message,
        )
        self.violations = violations


class AuthException(KnowhereException):
    """
    Authentication failed. HTTP 401.

    Details schema: {} (no additional details for security)
    """

    def __init__(
        self,
        message: str = "Authentication required",
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAUTHENTICATED,
            message=message,
            details={},  # Empty for security
            internal_message=internal_message,
        )


class PermissionException(KnowhereException):
    """
    Permission denied. HTTP 403.

    Details schema:
        {"required_permission": "..."}
    """

    def __init__(
        self,
        message: str = "Permission denied",
        required_permission: Optional[str] = None,
        internal_message: Optional[str] = None,
    ):
        details: Dict[str, Any] = {}
        if required_permission:
            details["required_permission"] = required_permission
        super().__init__(
            code=ErrorCode.PERMISSION_DENIED,
            message=message,
            details=details,
            internal_message=internal_message,
        )


class NotFoundException(KnowhereException):
    """
    Resource not found. HTTP 404.

    Details schema:
        {"resource": "...", "id": "..."}
    """

    def __init__(
        self,
        resource: str,
        resource_id: str,
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            details={"resource": resource, "id": resource_id},
            internal_message=internal_message,
        )


class ConflictException(KnowhereException):
    """
    Resource conflict (e.g., already exists, concurrent update). HTTP 409.

    Details schema:
        {"reason": "ALREADY_EXISTS" | "ABORTED", "resource": "...", "id": "..."}
    """

    def __init__(
        self,
        message: str,
        reason: SubCode,
        resource: Optional[str] = None,
        resource_id: Optional[str] = None,
        internal_message: Optional[str] = None,
    ):
        details: Dict[str, Any] = {"reason": reason.value}
        if resource:
            details["resource"] = resource
        if resource_id:
            details["id"] = resource_id
        super().__init__(
            code=ErrorCode.ALREADY_EXISTS if reason == SubCode.USER_NOT_FOUND else ErrorCode.ABORTED,
            message=message,
            details=details,
            internal_message=internal_message,
        )


class RateLimitException(KnowhereException):
    """
    Rate limit exceeded. HTTP 429. RETRYABLE.

    Details schema:
        {"reason": "RATE_LIMIT_EXCEEDED", "retry_after": <seconds>}
    """

    def __init__(
        self,
        retry_after: int,
        message: str = "Rate limit exceeded",
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.RESOURCE_EXHAUSTED,
            message=message,
            details={
                "reason": SubCode.RATE_LIMIT_EXCEEDED.value,
                "retry_after": retry_after,
            },
            internal_message=internal_message,
        )
        self.retry_after = retry_after


class QuotaExceededException(KnowhereException):
    """
    Quota exceeded. HTTP 429. NOT RETRYABLE.

    Details schema:
        {"reason": "QUOTA_EXCEEDED", "quota_name": "...", "limit": <int>}
    """

    def __init__(
        self,
        quota_name: str,
        limit: int,
        message: str = "Quota exceeded",
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.RESOURCE_EXHAUSTED,
            message=message,
            details={
                "reason": SubCode.QUOTA_EXCEEDED.value,
                "quota_name": quota_name,
                "limit": limit,
            },
            internal_message=internal_message,
        )


# ============================================================================
# Server Error Exceptions (5xx)
# ============================================================================


class UnavailableException(KnowhereException):
    """
    Service temporarily unavailable. HTTP 503. RETRYABLE.

    Details schema:
        {"retry_after": <seconds>}
    """

    def __init__(
        self,
        retry_after: int,
        message: str = "Service temporarily unavailable",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAVAILABLE,
            message=message,
            details={"retry_after": retry_after},
            internal_message=internal_message,
            original_exception=original_exception,
        )
        self.retry_after = retry_after


class TimeoutException(KnowhereException):
    """
    Request timed out. HTTP 504. RETRYABLE.

    Details schema:
        {"retry_after": <seconds>}
    """

    def __init__(
        self,
        retry_after: int,
        message: str = "Request timed out",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.DEADLINE_EXCEEDED,
            message=message,
            details={"retry_after": retry_after},
            internal_message=internal_message,
            original_exception=original_exception,
        )
        self.retry_after = retry_after


class UnknownException(KnowhereException):
    """
    Wrapper for non-KnowhereException errors. HTTP 500.
    Like a synatx error in the code.

    Use this to wrap unexpected exceptions so they conform to the API schema.
    Internal details are logged but NOT sent to client.

    Details schema: {} (empty for security)
    """

    def __init__(
        self,
        original_exception: Exception,
        message: str = "An unexpected error occurred",
    ):
        super().__init__(
            code=ErrorCode.UNKNOWN,
            message=message,
            details={},  # Empty for security
            internal_message=f"{type(original_exception).__name__}: {str(original_exception)}",
            original_exception=original_exception,
        )
