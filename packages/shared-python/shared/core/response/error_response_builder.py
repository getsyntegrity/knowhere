"""
Standard Error Response Builder.

Provides a consistent format for error responses across the application,
used by both API responses and webhook payloads.
"""

from typing import Any, Dict, Optional


def build_standard_error_response(
    code: str, message: str, request_id: str, details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a StandardErrorObject dictionary.

    This returns the same error structure as synchronous API errors,
    enabling clients to use the same error handling for both sync
    and async (job/webhook) errors.

    Args:
        code: Canonical error code (e.g., "VALIDATION_ERROR", "INTERNAL_ERROR")
        message: User-friendly error message
        request_id: Request/Job ID for tracing
        details: Optional structured error details (e.g., validation violations)

    Returns:
        Dict containing: code, message, request_id, and optionally details
    """
    error_response: Dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }

    if details:
        error_response["details"] = details

    return error_response
