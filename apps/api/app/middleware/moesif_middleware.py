"""
Moesif API monitoring middleware.
"""

import json
import time
from typing import Any, Dict, Optional

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from shared.core.config import settings


class MoesifMiddleware(BaseHTTPMiddleware):
    """Send request and response telemetry to Moesif."""

    def __init__(self, app, moesif_application_id: str = None):
        super().__init__(app)
        self.moesif_application_id = (
            moesif_application_id or settings.MOESIF_APPLICATION_ID
        )
        self.moesif_client = None

        if self.moesif_application_id:
            try:
                from moesifapi.configuration import Configuration
                from moesifapi.moesif_api_client import MoesifAPIClient

                configuration = Configuration()
                configuration.api_key = self.moesif_application_id

                self.moesif_client = MoesifAPIClient(configuration)
                logger.info("Initialized the Moesif client")

            except ImportError:
                logger.warning("Moesif SDK is not installed; skipping API monitoring")
            except Exception as e:
                logger.error(f"Failed to initialize the Moesif client: {e}")

    async def dispatch(self, request: Request, call_next):
        """Capture request/response telemetry for one request."""
        start_time = time.time()

        # Capture request information.
        request_data = await self._extract_request_data(request)

        # Run the downstream handler.
        response = await call_next(request)

        # Measure total processing time.
        process_time = time.time() - start_time

        # Capture response information.
        response_data = self._extract_response_data(response, process_time)

        # Send the event to Moesif when configured.
        if self.moesif_client:
            await self._send_to_moesif(request_data, response_data)

        return response

    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """Extract request metadata for Moesif."""
        try:
            # Read the request body when the method usually carries one.
            body = None
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    body = await request.body()
                    if body:
                        # Prefer decoded JSON when possible.
                        try:
                            body = json.loads(body.decode())
                        except:
                            # Fall back to a decoded string when the body is not JSON.
                            body = body.decode("utf-8", errors="ignore")
                except:
                    body = None

            # Read query parameters.
            query_params = dict(request.query_params)

            # Resolve the user identifier from auth or forwarded headers.
            user_id = await self._get_user_id(request)

            # Read the forwarded session token when present.
            session_token = request.headers.get("x-session-token")

            return {
                "time": int(time.time() * 1000),  # Millisecond timestamp.
                "uri": str(request.url),
                "verb": request.method,
                "headers": dict(request.headers),
                "api_version": request.headers.get("x-api-version", "1.0"),
                "ip_address": request.client.host if request.client else None,
                "user_id": user_id,
                "session_token": session_token,
                "body": body,
                "query_params": query_params,
            }

        except Exception as e:
            logger.error(f"Failed to extract request data: {e}")
            return {}

    def _extract_response_data(
        self, response: Response, process_time: float
    ) -> Dict[str, Any]:
        """Extract response metadata for Moesif."""
        try:
            return {
                "time": int(time.time() * 1000),
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": None,  # Response bodies are usually too large to store here.
                "transfer_encoding": response.headers.get("transfer-encoding"),
                "content_length": response.headers.get("content-length"),
                "process_time_ms": round(process_time * 1000, 2),
            }

        except Exception as e:
            logger.error(f"Failed to extract response data: {e}")
            return {}

    async def _get_user_id(self, request: Request) -> Optional[str]:
        """Resolve the user identifier for telemetry."""
        try:
            # Check the Authorization header first.
            auth_header = request.headers.get("authorization")
            if auth_header:
                if auth_header.startswith("Bearer "):
                    # JWT token.
                    token = auth_header[7:]
                    # TODO: Parse the JWT and extract the user ID.
                elif auth_header.startswith("ApiKey "):
                    # API key.
                    api_key = auth_header[7:]
                    # TODO: Resolve the user ID from the API key in the database.

            # Fall back to X-User-ID when the frontend provides it.
            return request.headers.get("x-user-id")

        except Exception as e:
            logger.error(f"Failed to resolve user ID: {e}")
            return None

    async def _send_to_moesif(
        self, request_data: Dict[str, Any], response_data: Dict[str, Any]
    ):
        """Send one event to Moesif."""
        try:
            if not self.moesif_client:
                return

            # Build the Moesif event payload.
            event = {
                "request": request_data,
                "response": response_data,
                "user_id": request_data.get("user_id"),
                "session_token": request_data.get("session_token"),
                "tags": self._get_event_tags(request_data, response_data),
                "metadata": self._get_event_metadata(request_data, response_data),
            }

            # Send asynchronously without blocking the request.
            import asyncio

            asyncio.create_task(self._send_event_async(event))

        except Exception as e:
            logger.error(f"Failed to send Moesif event: {e}")

    async def _send_event_async(self, event: Dict[str, Any]):
        """Send one event to Moesif asynchronously."""
        try:
            # Moesif's Python SDK is synchronous, so send it in a thread pool.
            import asyncio
            import concurrent.futures

            def send_sync():
                try:
                    # Use whichever send method the installed client exposes.
                    if hasattr(self.moesif_client, "create_event"):
                        self.moesif_client.create_event(event)
                    elif hasattr(self.moesif_client, "create_events"):
                        self.moesif_client.create_events([event])
                    else:
                        logger.warning(
                            "The Moesif client does not expose create_event or create_events"
                        )
                except Exception as e:
                    logger.error(f"Synchronous Moesif send failed: {e}")

            # Run the synchronous client call in a thread pool.
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, send_sync)

        except Exception as e:
            logger.error(f"Async Moesif send failed: {e}")

    def _get_event_tags(
        self, request_data: Dict[str, Any], response_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """Build event tags for Moesif analytics."""
        tags = {}

        # Tag by feature area.
        uri = request_data.get("uri", "")
        if "/kb" in uri:
            tags["feature"] = "knowledge_base"
        elif "/billing" in uri:
            tags["feature"] = "billing"
        elif "/auth" in uri:
            tags["feature"] = "authentication"

        # Tag by response status family.
        status = response_data.get("status", 200)
        if 200 <= status < 300:
            tags["status"] = "success"
        elif 400 <= status < 500:
            tags["status"] = "client_error"
        elif 500 <= status < 600:
            tags["status"] = "server_error"

        return tags

    def _get_event_metadata(
        self, request_data: Dict[str, Any], response_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build event metadata for Moesif analytics."""
        metadata = {}

        # Include total processing time.
        process_time = response_data.get("process_time_ms", 0)
        metadata["process_time_ms"] = process_time

        # Include request size when known.
        body = request_data.get("body")
        if body:
            if isinstance(body, str):
                metadata["request_size_bytes"] = len(body.encode())
            elif isinstance(body, dict):
                metadata["request_size_bytes"] = len(json.dumps(body).encode())

        # Include response size when known.
        content_length = response_data.get("content_length")
        if content_length:
            metadata["response_size_bytes"] = int(content_length)

        return metadata
