"""
Request logging middleware with structured logging support.
Pure ASGI implementation to avoid BaseHTTPMiddleware body buffering.
"""
import time
import uuid

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared.core.logging import log_context, LogEvent

SKIP_PATHS = {"/health", "/api/health"}


class LoggingMiddleware:
    """Request logging middleware with structured context propagation."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        # Extract or generate request_id
        headers = dict(
            (k.decode("latin-1"), v.decode("latin-1"))
            for k, v in scope.get("headers", [])
        )
        request_id = headers.get("x-request-id", str(uuid.uuid4()))

        # Make request_id available via request.state.request_id
        # scope["state"] must be a plain dict — Starlette's Request.state
        # wraps it in a State object for attribute access.
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        start_time = time.time()
        status_code = 500  # default in case of unhandled error

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # Inject X-Request-ID header
                raw_headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"x-request-id"
                ]
                raw_headers.append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
                message["headers"] = raw_headers
            await send(message)

        with log_context(request_id=request_id):
            await self.app(scope, receive, send_wrapper)

            duration_ms = (time.time() - start_time) * 1000
            user_id = scope.get("state", {}).get("user_id")

            completion_log = logger.bind(
                event=LogEvent.HTTP_REQUEST_COMPLETE.value,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
            )
            if user_id:
                completion_log = completion_log.bind(user_id=user_id)
            completion_log.info("HTTP request completed")
