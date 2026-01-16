"""
Domain-specific exceptions with typed details schemas.

=============================================================================
SECURITY: THE "4xx vs 5xx" MESSAGE PATTERN
=============================================================================

Each exception follows the dual-message pattern:

    - `internal_message`: Technical details for LOGS ONLY. NEVER sent to client.
    - `user_message`:     Safe message for CLIENT. ALWAYS sent to user.

4xx Exceptions (Client Errors):
    - Developer MUST provide `user_message` (helpful for user to fix their input)
    - `internal_message` is optional (for extra debugging context)

5xx Exceptions (System Errors):
    - Developer provides `internal_message` for debugging
    - `user_message` auto-defaults to generic safe message
    - Developer CAN override with custom safe `user_message`

=============================================================================

Each exception has a fixed `details` structure that clients can rely on.
Do NOT raise KnowhereException directly - use these domain exceptions.

Usage (4xx - Client Error):
    from shared.core.exceptions import ValidationException

    raise ValidationException(
        user_message="The file 'data.csv' is too large (max 5MB).",
        violations=[{"field": "file", "description": "Exceeds 5MB limit"}]
    )

Usage (5xx - System Error):
    from shared.core.exceptions import FileSystemException

    raise FileSystemException(
        internal_message="Permission denied: cannot write to /var/lib/worker/tmp",
        operation="write"
    )
    # User sees: "An internal system error occurred. Please contact support."
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
# ----------------------------------------------------------------------------
# For 4xx errors, developer MUST provide `user_message` that helps the user
# understand and fix their input error. `internal_message` is optional.
# ============================================================================


class ValidationException(KnowhereException):
    """
    Invalid input from client. HTTP 400.

    4xx Error: Developer provides `user_message` that user sees directly.

    Details schema:
        {"violations": [{"field": "...", "description": "..."}]}
    """

    def __init__(
        self,
        user_message: str,
        violations: List[Violation],
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={"violations": violations},
        )
        self.violations = violations


class AuthException(KnowhereException):
    """
    Authentication failed. HTTP 401.

    4xx Error: Developer provides `user_message` that user sees directly.

    Details schema: {} (no additional details for security)
    """

    def __init__(
        self,
        user_message: str = "Authentication required",
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAUTHENTICATED,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={},  # Empty for security
        )


class PermissionException(KnowhereException):
    """
    Permission denied. HTTP 403.

    4xx Error: Developer provides `user_message` that user sees directly.

    Details schema:
        {"required_permission": "..."}
    """

    def __init__(
        self,
        user_message: str = "Permission denied",
        required_permission: Optional[str] = None,
        internal_message: Optional[str] = None,
    ):
        details: Dict[str, Any] = {}
        if required_permission:
            details["required_permission"] = required_permission
        super().__init__(
            code=ErrorCode.PERMISSION_DENIED,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details=details,
        )


class NotFoundException(KnowhereException):
    """
    Resource not found. HTTP 404.

    4xx Error: Auto-generates user_message from resource name.

    Details schema:
        {"resource": "...", "id": "..."}
    """

    def __init__(
        self,
        resource: str,
        resource_id: str,
        internal_message: Optional[str] = None,
    ):
        user_msg = f"{resource} not found"
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            internal_message=internal_message or f"{resource} with id={resource_id} not found",
            user_message=user_msg,
            details={"resource": resource, "id": resource_id},
        )


class ConflictException(KnowhereException):
    """
    Resource conflict (e.g., already exists, concurrent update). HTTP 409.

    4xx Error: Developer provides `user_message` that user sees directly.

    Details schema:
        {"reason": "ALREADY_EXISTS" | "ABORTED", "resource": "...", "id": "..."}
    """

    def __init__(
        self,
        user_message: str,
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
            internal_message=internal_message or user_message,
            user_message=user_message,
            details=details,
        )


class RateLimitException(KnowhereException):
    """
    Rate limit exceeded. HTTP 429. RETRYABLE.

    4xx Error: Developer provides `user_message` that user sees directly.

    Details schema:
        {"reason": "RATE_LIMIT_EXCEEDED", "retry_after": <seconds>}
    """

    def __init__(
        self,
        retry_after: int,
        user_message: str = "Rate limit exceeded. Please slow down.",
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.RESOURCE_EXHAUSTED,
            internal_message=internal_message or f"Rate limit exceeded, retry_after={retry_after}s",
            user_message=user_message,
            details={
                "reason": SubCode.RATE_LIMIT_EXCEEDED.value,
                "retry_after": retry_after,
            },
        )
        self.retry_after = retry_after


class QuotaExceededException(KnowhereException):
    """
    Quota exceeded. HTTP 429. NOT RETRYABLE.

    4xx Error: Developer provides `user_message` that user sees directly.

    Details schema:
        {"reason": "QUOTA_EXCEEDED", "quota_name": "...", "limit": <int>}
    """

    def __init__(
        self,
        quota_name: str,
        limit: int,
        user_message: str = "Quota exceeded",
        internal_message: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.RESOURCE_EXHAUSTED,
            internal_message=internal_message or f"Quota {quota_name} exceeded, limit={limit}",
            user_message=user_message,
            details={
                "reason": SubCode.QUOTA_EXCEEDED.value,
                "quota_name": quota_name,
                "limit": limit,
            },
        )


# ============================================================================
# Server Error Exceptions (5xx)
# ----------------------------------------------------------------------------
# For 5xx errors, developer provides `internal_message` for debugging.
# `user_message` auto-defaults to a safe generic message.
# Developer CAN override `user_message` with a custom safe message.
# ============================================================================


class UnavailableException(KnowhereException):
    """
    Service temporarily unavailable. HTTP 503. RETRYABLE.

    5xx Error: Auto-defaults to safe user_message.

    Details schema:
        {"retry_after": <seconds>}
    """

    def __init__(
        self,
        internal_message: str,
        retry_after: int,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAVAILABLE,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={"retry_after": retry_after},
            original_exception=original_exception,
        )
        self.retry_after = retry_after


class TimeoutException(KnowhereException):
    """
    Request timed out. HTTP 504. RETRYABLE.

    5xx Error: Auto-defaults to safe user_message.

    Details schema:
        {"retry_after": <seconds>}
    """

    def __init__(
        self,
        internal_message: str,
        retry_after: int,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.DEADLINE_EXCEEDED,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={"retry_after": retry_after},
            original_exception=original_exception,
        )
        self.retry_after = retry_after


class UnknownException(KnowhereException):
    """
    Wrapper for non-KnowhereException errors. HTTP 500.
    Like a syntax error in the code.

    5xx Error: Auto-defaults to safe user_message.
    Internal details are logged but NEVER sent to client.

    Use this to wrap unexpected exceptions so they conform to the API schema.

    Details schema: {} (empty for security)
    """

    def __init__(
        self,
        original_exception: Exception,
        user_message: str = "An unexpected error occurred",
    ):
        super().__init__(
            code=ErrorCode.UNKNOWN,
            internal_message=f"{type(original_exception).__name__}: {str(original_exception)}",
            user_message=user_message,
            details={},  # Empty for security
            original_exception=original_exception,
        )


# ============================================================================
# Worker-Specific Exceptions (5xx)
# ----------------------------------------------------------------------------
# These are system errors that occur during async worker processing.
# Developer provides `internal_message`; `user_message` auto-defaults.
# ============================================================================


class FileSystemException(KnowhereException):
    """
    File system operation failed (read, write, create directory). HTTP 500.

    5xx Error: Auto-defaults to safe user_message.
    
    SECURITY: `path` is stored internally but NOT exposed in details.

    Details schema:
        {"operation": "read" | "write" | "create_directory" | "delete"}
    """

    def __init__(
        self,
        internal_message: str,
        operation: str,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        # SECURITY: Do NOT include path in details (internal info)
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={"operation": operation},
            original_exception=original_exception,
        )


class PDFParsingException(KnowhereException):
    """
    PDF parsing failed (encrypted, corrupted, layout issues).

    4xx Error: User's file is problematic; they need to fix it.
    Developer provides `user_message` that user sees directly.

    Details schema:
        {"file_type": "pdf", "reason": "..."}
    """

    def __init__(
        self,
        user_message: str,
        reason: str = "PARSING_FAILED",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={"file_type": "pdf", "reason": reason},
            original_exception=original_exception,
        )


class DocxParsingException(KnowhereException):
    """
    DOCX parsing failed (structure issues).

    4xx Error: User's file is problematic; they need to fix it.
    Developer provides `user_message` that user sees directly.

    Details schema:
        {"file_type": "docx", "reason": "..."}
    """

    def __init__(
        self,
        user_message: str,
        reason: str = "PARSING_FAILED",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={"file_type": "docx", "reason": reason},
            original_exception=original_exception,
        )


class TableParsingException(KnowhereException):
    """
    Table extraction failed.

    4xx Error: User's file is problematic; they need to fix it.
    Developer provides `user_message` that user sees directly.

    Details schema:
        {"file_type": "table", "reason": "..."}
    """

    def __init__(
        self,
        user_message: str,
        reason: str = "PARSING_FAILED",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={"file_type": "table", "reason": reason},
            original_exception=original_exception,
        )


class ImageParsingException(KnowhereException):
    """
    Image processing/OCR failed.

    4xx Error: User's file is problematic; they need to fix it.
    Developer provides `user_message` that user sees directly.

    Details schema:
        {"file_type": "image", "reason": "..."}
    """

    def __init__(
        self,
        user_message: str,
        reason: str = "PARSING_FAILED",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={"file_type": "image", "reason": reason},
            original_exception=original_exception,
        )


class TextParsingException(KnowhereException):
    """
    Text decoding or format failed.

    4xx Error: User's file is problematic; they need to fix it.
    Developer provides `user_message` that user sees directly.

    Details schema:
        {"file_type": "text", "reason": "..."}
    """

    def __init__(
        self,
        user_message: str,
        reason: str = "PARSING_FAILED",
        internal_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            internal_message=internal_message or user_message,
            user_message=user_message,
            details={"file_type": "text", "reason": reason},
            original_exception=original_exception,
        )


class LLMServiceException(KnowhereException):
    """
    LLM service call failed.

    5xx Error: Auto-defaults to safe user_message.

    Details schema:
        {"service": "...", "status_code": <int>}
    """

    def __init__(
        self,
        internal_message: str,
        provider: str = "llm",
        status_code: Optional[int] = None,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        details: Dict[str, Any] = {"service": provider}
        if status_code is not None:
            details["status_code"] = status_code
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details=details,
            original_exception=original_exception,
        )


class StorageServiceException(KnowhereException):
    """
    Storage service (S3/MinIO) failed.

    5xx Error: Auto-defaults to safe user_message.

    Details schema:
        {"service": "storage", "operation": "..."}
    """

    def __init__(
        self,
        internal_message: str,
        operation: str = "unknown",
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={"service": "storage", "operation": operation},
            original_exception=original_exception,
        )


class RedisServiceException(KnowhereException):
    """
    Redis/Cache service failed.

    5xx Error: Auto-defaults to safe user_message.

    Details schema:
        {"service": "redis", "operation": "..."}
    """

    def __init__(
        self,
        internal_message: str,
        operation: str = "unknown",
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={"service": "redis", "operation": operation},
            original_exception=original_exception,
        )


class MinerUServiceException(KnowhereException):
    """
    MinerU PDF extraction service failed.

    5xx Error: Auto-defaults to safe user_message.

    Details schema:
        {"service": "mineru", "status_code": <int>, "error_message": "..."}
    """

    def __init__(
        self,
        internal_message: str,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        details: Dict[str, Any] = {"service": "mineru"}
        if status_code is not None:
            details["status_code"] = status_code
        # SECURITY: error_message might contain sensitive info, don't include in details
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details=details,
            original_exception=original_exception,
        )


class WorkerHandlingException(KnowhereException):
    """
    Worker handling failed (internal logic error).

    5xx Error: Auto-defaults to safe user_message.

    Details schema: {} (empty for security)
    """

    def __init__(
        self,
        internal_message: str,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={},
            original_exception=original_exception,
        )


class SystemSettingMissingException(KnowhereException):
    """
    Required system setting is missing.

    5xx Error: Auto-defaults to safe user_message.

    Details schema: {} (empty for security)
    """

    def __init__(
        self,
        internal_message: str,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={},
            original_exception=original_exception,
        )


class SystemSettingInvalidException(KnowhereException):
    """
    System setting has an invalid value.

    5xx Error: Auto-defaults to safe user_message.

    Details schema: {} (empty for security)
    """

    def __init__(
        self,
        internal_message: str,
        user_message: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            internal_message=internal_message,
            user_message=user_message,  # Defaults to generic 5xx message
            details={},
            original_exception=original_exception,
        )