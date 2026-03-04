"""
Request logging middleware with structured logging support.
"""
import time
import uuid

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from shared.core.logging import log_context, LogEvent


class LoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware with structured context propagation."""

    async def dispatch(self, request: Request, call_next):
        # Filter health check endpoints
        if request.url.path in ["/health", "/api/health"]:
            return await call_next(request)

        # Generate or extract request_id
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        start_time = time.time()

        # Set log context for this request
        with log_context(
            request_id=request_id,
            http_method=request.method,
        ):
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            user_id = getattr(request.state, "user_id", None)

            response.headers["X-Request-ID"] = request_id

            # Log request complete
            completion_log = logger.bind(
                event=LogEvent.HTTP_REQUEST_COMPLETE.value,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2)
            )
            if user_id:
                completion_log = completion_log.bind(user_id=user_id)
            completion_log.info("HTTP request completed")

            return response
