"""
Base Exception class for the Knowhere API.

WARNING: DO NOT RAISE THIS CLASS DIRECTLY IN YOUR CODE.

This is an abstract base class. Always use the domain-specific exceptions
from `shared.core.exceptions.DomainExceptions`:

    - ValidationException  (400 - invalid input with violations)
    - AuthException        (401 - authentication failed)
    - PermissionException  (403 - permission denied)
    - NotFoundException    (404 - resource not found)
    - RateLimitException   (429 - rate limit, retryable)
    - QuotaExceededException (429 - quota, NOT retryable)
    - UnavailableException (503 - service down, retryable)
    - TimeoutException     (504 - timeout, retryable)
    - UnknownException     (500 - wrap unexpected errors)

Correct Usage:
    from shared.core.exceptions import ValidationException, RateLimitException

    raise ValidationException(
        message="Invalid input",
        violations=[{"field": "email", "description": "Must be valid email"}]
    )

    raise RateLimitException(retry_after=15)

Wrong Usage:
    # DO NOT DO THIS:
    raise KnowhereException(code=ErrorCode.INVALID_ARGUMENT, ...)
"""

from typing import Any, Dict, Optional, Union

from shared.core.response.ErrorCode import ErrorCode, SubCode, ErrorCodeMapper


class KnowhereException(Exception):
    """
    Abstract base class for all Knowhere API exceptions.

    WARNING: DO NOT INSTANTIATE OR RAISE THIS CLASS DIRECTLY.
    Use domain-specific subclasses from DomainExceptions.py instead.

    This class provides:
    - to_dict(): Machine-readable JSON for API responses (client-facing)
    - to_log_dict(): Detailed info for internal logging (NOT sent to client)

    Adheres to the 3 Rules:
    1. Be Explicit - Use specific domain exceptions
    2. Machine Readable - to_dict() returns consistent JSON schema
    3. Security First - Internal details stay in exception, not in response

    Attributes:
        code: Canonical error code (determines HTTP status)
        message: Human-readable message for the client
        details: Client-facing structured data (e.g., retry_after, reason)
        http_status_code: HTTP status (auto-derived from code if not specified)
        original_exception: Wrapped exception for logging (NOT sent to client)
        internal_message: Detailed message for logging (NOT sent to client)
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        http_status_code: Optional[int] = None,
        original_exception: Optional[Exception] = None,
        internal_message: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status_code = http_status_code or ErrorCodeMapper.get_http_status_from_error_code(
            code
        )
        # Internal fields for logging - NOT exposed to client
        self.original_exception = original_exception
        self.internal_message = internal_message

    def to_dict(self, request_id: str) -> Dict[str, Any]:
        """
        Returns a machine-readable JSON representation for API responses.
        This is the ONLY data that gets sent to the client.
        """
        response: Dict[str, Any] = {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "request_id": request_id,
            },
        }
        # Only include details if non-empty
        if self.details:
            response["error"]["details"] = self.details
        return response

    def to_log_dict(self) -> Dict[str, Any]:
        """
        Returns a detailed representation for internal logging.
        Includes internal_message and original_exception info.
        """
        log_data: Dict[str, Any] = {
            "error_code": self.code.value,
            "message": self.message,
            "http_status": self.http_status_code,
            "details": self.details,
        }
        if self.internal_message:
            log_data["internal_message"] = self.internal_message
        if self.original_exception:
            log_data["original_exception"] = {
                "type": type(self.original_exception).__name__,
                "message": str(self.original_exception),
            }
        return log_data

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.code.value!r}, "
            f"message={self.message!r}, "
            f"http_status={self.http_status_code})"
        )
