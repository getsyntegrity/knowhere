"""
Global Exception Handlers for the Knowhere API.

All exceptions are converted to KnowhereException and handled uniformly.
This ensures clients always receive a consistent, secure JSON response.

Architecture:
    1. Each handler converts its exception type to a KnowhereException subclass
    2. All handlers delegate to `knowhere_exception_handler` for actual response
    3. Internal details are logged but NEVER sent to client

Response Format:
    {
        "success": false,
        "error": {
            "code": "INVALID_ARGUMENT",
            "message": "Human-readable error",
            "request_id": "req_abc123",
            "details": {...}  // Optional, schema varies by exception type
        }
    }

Exception Sources:
    - KnowhereException: Raised explicitly by our code (domain exceptions)
    - HTTPException: Raised by FastAPI/Starlette for HTTP-level errors
        - 401: Missing/invalid auth header
        - 403: Permission denied by middleware
        - 404: Route not found
        - 405: Method not allowed
    - RequestValidationError: Raised by Pydantic when request body/params invalid
    - Exception: Unexpected errors (bugs, syntax errors, external failures)
"""

import uuid
import traceback
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.core.exceptions import (
    KnowhereException,
    ValidationException,
    UnknownException,
)
from shared.core.response import ErrorCode, ErrorCodeMapper


def _get_request_id(request: Request) -> str:
    """Extract or generate a request ID for tracing."""
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


async def knowhere_exception_handler(
    request: Request, exc: KnowhereException
) -> JSONResponse:
    """
    Central handler for ALL KnowhereException subclasses.
    
    This is the ONLY place that builds the actual response.
    All other handlers convert their exceptions and delegate here.
    
    Logging:
        - 5xx: ERROR level with stack trace (if original_exception exists)
        - 4xx: WARNING level
    
    The `original_exception` field is used to:
        1. Log the underlying cause for debugging (e.g., Redis timeout)
        2. Include stack trace in logs without exposing to client
        3. Wrap unexpected exceptions while preserving debug info
    """
    request_id = _get_request_id(request)

    # Log based on severity
    log_data = exc.to_log_dict()
    if exc.http_status_code >= 500:
        logger.error(
            f"[{request_id}] System Error: {exc.code.value} - {exc.message}",
            **log_data,
        )
        # Log stack trace if we wrapped an unexpected exception
        if exc.original_exception:
            logger.error(f"[{request_id}] Original exception: {traceback.format_exc()}")
    else:
        logger.warning(
            f"[{request_id}] Client Error: {exc.code.value} - {exc.message}",
            **log_data,
        )

    # Build response with optional Retry-After header
    headers = {}
    if hasattr(exc, "retry_after") and exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=exc.http_status_code,
        content=exc.to_dict(request_id),
        headers=headers if headers else None,
    )


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """
    Convert FastAPI/Starlette HTTPException to KnowhereException.
    
    When does HTTPException occur?
        - 401: Auth middleware rejects request (missing/invalid token)
        - 403: Permission check fails
        - 404: No route matches the path
        - 405: HTTP method not allowed for this route
        - 422: Handled separately by validation_exception_handler
    
    Security: HTTPException.detail may contain sensitive info from middleware.
    We use a generic message and log the original internally.
    """
    # Convert HTTP status to ErrorCode using the canonical mapping
    code = ErrorCodeMapper.get_error_code_from_http_status(exc.status_code)
    
    # Generic safe messages for each status (no detail leak)
    safe_messages = {
        400: "Bad request",
        401: "Authentication required",
        403: "Permission denied",
        404: "Resource not found",
        405: "Method not allowed",
        409: "Conflict",
        429: "Too many requests",
        500: "Internal server error",
        502: "Bad gateway",
        503: "Service unavailable",
        504: "Gateway timeout",
    }
    safe_message = safe_messages.get(exc.status_code, "An error occurred")
    
    # Create KnowhereException (log original detail internally)
    knowhere_exc = KnowhereException(
        code=code,
        message=safe_message,
        internal_message=f"HTTPException detail: {exc.detail}",
    )
    
    # Delegate to central handler
    return await knowhere_exception_handler(request, knowhere_exc)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Convert Pydantic validation errors to ValidationException.
    
    When does RequestValidationError occur?
        - Request body doesn't match Pydantic model
        - Query/path parameters fail validation
        - Type coercion fails (e.g., string where int expected)
    
    The violations array IS safe to expose as it describes client input issues.
    """
    # Transform Pydantic errors into violations format
    violations: List[dict] = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        violations.append({
            "field": field,
            "description": error.get("msg", "Validation failed"),
        })

    # Create ValidationException
    validation_exc = ValidationException(
        message="Request validation failed",
        violations=violations,
    )
    
    # Delegate to central handler
    return await knowhere_exception_handler(request, validation_exc)


async def general_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all for unexpected exceptions.
    
    When does this occur?
        - Syntax errors, bugs in code
        - Unhandled third-party library exceptions
        - Database/Redis connection failures not wrapped by our code
    
    Security: NEVER expose exception details to client.
    The `original_exception` is stored for internal logging only.
    """
    # Wrap in UnknownException - this logs internally, returns generic message
    unknown_exc = UnknownException(original_exception=exc)
    
    # Delegate to central handler
    return await knowhere_exception_handler(request, unknown_exc)


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI app.
    
    Order of registration doesn't matter - FastAPI matches by exception type.
    More specific types (KnowhereException subclasses) are matched before base.
    """
    # KnowhereException and all subclasses
    app.add_exception_handler(KnowhereException, knowhere_exception_handler)

    # FastAPI/Starlette HTTP exceptions (convert then delegate)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Pydantic validation errors (convert then delegate)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Catch-all for unexpected exceptions (MUST be last conceptually)
    app.add_exception_handler(Exception, general_exception_handler)

    logger.info("Global exception handlers registered (KnowhereException flow enabled)")
