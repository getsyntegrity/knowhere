"""
Resolve file extension from a URL.

Tries the URL path first, then falls back to a HEAD request to read Content-Type.
Provides both async (for API) and sync (for worker) variants.
"""

import os
from urllib.parse import urlparse

from loguru import logger

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import ValidationException
from shared.utils.url_security import (
    MAX_SAFE_REDIRECTS,
    SafePublicHTTPURL,
    get_safe_public_http_url,
    validate_public_http_redirect_url,
)

# Content-Type to file extension mapping
CONTENT_TYPE_TO_EXTENSION: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
}

REDIRECT_STATUS_CODES: set[int] = {301, 302, 303, 307, 308}


def _extension_from_path(url: str) -> str | None:
    """Extract a recognised file extension from the URL path."""
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext and ext in settings.get_supported_extensions():
        return ext
    return None


def _extension_from_content_type(content_type: str | None) -> str | None:
    """Map a Content-Type header value to a supported file extension."""
    if not content_type:
        return None
    # Strip parameters like "; charset=utf-8"
    mime = content_type.split(";")[0].strip().lower()
    ext = CONTENT_TYPE_TO_EXTENSION.get(mime)
    if ext and ext in settings.get_supported_extensions():
        return ext
    return None


async def resolve_file_extension_async(url: str) -> str | None:
    """
    Resolve file extension from a URL (async version for API layer).

    1. Try extracting extension from URL path.
    2. If that fails, send a HEAD request and read Content-Type.
    3. Return None if neither method produces a supported extension.
    """
    safe_url = get_safe_public_http_url(url, field="source_url")

    ext = _extension_from_path(safe_url)
    if ext:
        return ext

    try:
        from shared.utils.http_clients import get_async_client

        client = get_async_client()
        response = None
        request_url: SafePublicHTTPURL = safe_url
        for _ in range(MAX_SAFE_REDIRECTS + 1):
            response = await client.head(request_url, follow_redirects=False)
            if response.status_code not in REDIRECT_STATUS_CODES:
                break

            location = response.headers.get("location")
            if not location:
                break
            request_url = validate_public_http_redirect_url(
                request_url,
                location,
                field="source_url",
            )

        if response is None:
            return None
        content_type = response.headers.get("content-type")
        ext = _extension_from_content_type(content_type)
        if ext:
            logger.info(
                f"Resolved file extension from Content-Type header: {ext}"
            )
            return ext
    except ValidationException:
        raise
    except Exception as exc:
        logger.warning(
            f"HEAD request failed for URL file type detection: {exc}"
        )

    return None


def resolve_file_extension_sync(url: str) -> str | None:
    """
    Resolve file extension from a URL (sync version for worker layer).

    Same logic as async variant but uses the shared sync httpx client.
    """
    safe_url = get_safe_public_http_url(url, field="source_url")

    ext = _extension_from_path(safe_url)
    if ext:
        return ext

    try:
        from shared.utils.http_clients import get_sync_client

        client = get_sync_client()
        response = None
        request_url: SafePublicHTTPURL = safe_url
        for _ in range(MAX_SAFE_REDIRECTS + 1):
            response = client.head(request_url, follow_redirects=False)
            if response.status_code not in REDIRECT_STATUS_CODES:
                break

            location = response.headers.get("location")
            if not location:
                break
            request_url = validate_public_http_redirect_url(
                request_url,
                location,
                field="source_url",
            )

        if response is None:
            return None
        content_type = response.headers.get("content-type")
        ext = _extension_from_content_type(content_type)
        if ext:
            logger.info(
                f"Resolved file extension from Content-Type header: {ext}"
            )
            return ext
    except ValidationException:
        raise
    except Exception as exc:
        logger.warning(
            f"HEAD request failed for URL file type detection: {exc}"
        )

    return None
