"""
Base Exception class for the Knowhere API.

=============================================================================
SECURITY RULE: THE "4xx vs 5xx" MESSAGE PATTERN
=============================================================================

This class implements a dual-message pattern for security and developer experience:

    - `internal_message`: Technical details for LOGS ONLY. NEVER sent to client.
    - `user_message`:     Safe message for CLIENT. ALWAYS sent to user.

For 5xx (System Errors):
    - Developer provides `internal_message` for debugging (e.g., "Disk full on /mnt/data")
    - System auto-generates safe `user_message` (e.g., "Internal system error...")
    - Developer CAN override `user_message` for specific safe messages

For 4xx (Client Errors):
    - Developer provides `user_message` that helps user fix their input
    - `internal_message` is optional (for extra debugging context)

=============================================================================
WARNING: DO NOT RAISE THIS CLASS DIRECTLY IN YOUR CODE.
=============================================================================

This is an abstract base class. Always use the domain-specific exceptions
from `shared.core.exceptions.domain_exceptions`:

    - ValidationException  (400 - invalid input with violations)
    - AuthException        (401 - authentication failed)
    - PermissionException  (403 - permission denied)
    - NotFoundException    (404 - resource not found)
    - RateLimitException   (429 - rate limit, retryable)
    - QuotaExceededException (429 - quota, NOT retryable)
    - UnavailableException (503 - service down, retryable)
    - TimeoutException     (504 - timeout, retryable)
    - UnknownException     (500 - wrap unexpected errors)

Correct Usage (4xx - Client Error):
    from shared.core.exceptions import ValidationException

    raise ValidationException(
        user_message="The file 'data.csv' is too large (max 5MB).",
        violations=[{"field": "file", "description": "Exceeds 5MB limit"}]
    )

Correct Usage (5xx - System Error):
    from shared.core.exceptions import FileSystemException

    raise FileSystemException(
        internal_message="Permission denied: cannot write to /var/lib/worker/tmp",
        operation="write"
    )
    # User sees: "An internal system error occurred. Please contact support."
    # Logs see: "Permission denied: cannot write to /var/lib/worker/tmp"

Wrong Usage:
    # DO NOT DO THIS:
    raise KnowhereException(code=ErrorCode.INVALID_ARGUMENT, ...)
"""

from typing import Any, Dict, Optional

from shared.core.response.ErrorCode import ErrorCode, ErrorCodeMapper


# Default messages for auto-sanitization
DEFAULT_5XX_USER_MESSAGE = "An internal system error occurred. Please contact support."
DEFAULT_4XX_USER_MESSAGE = "Invalid request. Please check your input."


class KnowhereException(Exception):
    """
    Abstract base class for all Knowhere API exceptions.

    ==========================================================================
    SECURITY: THE DUAL-MESSAGE PATTERN
    ==========================================================================

    This class enforces a strict separation between:
    
    1. `internal_message` - Technical details for DEBUGGING (logs only)
       - Contains specific error info (paths, IDs, stack traces)
       - NEVER exposed to the client (security risk)
       - Used by developers/ops to diagnose issues
    
    2. `user_message` - Safe message for the CLIENT
       - Contains user-friendly, actionable information
       - ALWAYS returned in API response
       - For 5xx: Auto-defaults to generic safe message
       - For 4xx: Developer must provide helpful message

    ==========================================================================

    WARNING: DO NOT INSTANTIATE OR RAISE THIS CLASS DIRECTLY.
    Use domain-specific subclasses from domain_exceptions.py instead.

    This class provides:
    - to_dict(): Machine-readable JSON for API responses (returns user_message)
    - to_log_dict(): Detailed info for internal logging (includes internal_message)

    Adheres to the 3 Rules + Security:
    1. Be Explicit - Use specific domain exceptions
    2. Machine Readable - to_dict() returns consistent JSON schema
    3. Security First - internal_message NEVER in response; only user_message

    Attributes:
        code: Canonical error code (determines HTTP status)
        user_message: Safe, user-friendly message (ALWAYS sent to client)
        internal_message: Technical details for logging (NEVER sent to client)
        details: Client-facing structured data (e.g., retry_after, reason)
        http_status_code: HTTP status (auto-derived from code if not specified)
        original_exception: Wrapped exception for logging (NOT sent to client)
    """

    def __init__(
        self,
        code: ErrorCode,
        internal_message: str,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        http_status_code: Optional[int] = None,
        original_exception: Optional[Exception] = None,
    ):
        """
        Initialize a KnowhereException.

        Args:
            code: The canonical ErrorCode for this exception.
            internal_message: Technical message for logs. NEVER sent to client.
            user_message: Safe message for client. Auto-defaults based on HTTP status:
                - 5xx: Defaults to "An internal system error occurred..."
                - 4xx: Defaults to "Invalid request. Please check your input."
            details: Optional structured data to include in response (must be safe).
            http_status_code: Override HTTP status (auto-derived from code if None).
            original_exception: The underlying exception being wrapped (for logging).
        """
        super().__init__(internal_message)
        self.code = code
        self.internal_message = internal_message
        self.details = details or {}
        self.http_status_code = http_status_code or ErrorCodeMapper.get_http_status_from_error_code(
            code
        )
        self.original_exception = original_exception

        # =======================================================================
        # SECURITY: Auto-sanitize user_message based on HTTP status
        # =======================================================================
        # For 5xx (system errors): Default to generic safe message
        # For 4xx (client errors): Default to generic safe message
        # Domain exceptions SHOULD always provide explicit user_message
        if self.http_status_code >= 500:
            self.user_message = user_message or DEFAULT_5XX_USER_MESSAGE
        else:
            self.user_message = user_message or DEFAULT_4XX_USER_MESSAGE

    def to_dict(self, request_id: str) -> Dict[str, Any]:
        """
        Returns a machine-readable JSON representation for API responses.
        
        SECURITY: This method returns `user_message`, NEVER `internal_message`.
        This is the ONLY data that gets sent to the client.
        """
        response: Dict[str, Any] = {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.user_message,  # SECURITY: Only user_message exposed
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
        This data is for server-side logging ONLY, never sent to client.
        """
        log_data: Dict[str, Any] = {
            "error_code": self.code.value,
            "user_message": self.user_message,
            "internal_message": self.internal_message,  # For debugging
            "http_status": self.http_status_code,
            "details": self.details,
        }
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
            f"user_message={self.user_message!r}, "
            f"http_status={self.http_status_code})"
        )
