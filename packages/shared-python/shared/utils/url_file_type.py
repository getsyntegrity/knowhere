"""
Resolve file extension from a URL.

Tries the URL path first, then falls back to a HEAD request to read Content-Type.
Provides both async (for API) and sync (for worker) variants.
"""

import os
from urllib.parse import urlparse

from loguru import logger

from shared.core.config import settings
from shared.utils.url_security import validate_public_http_url

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
    validate_public_http_url(url, field="source_url")

    ext = _extension_from_path(url)
    if ext:
        return ext

    try:
        from shared.utils.http_clients import get_async_client

        client = get_async_client()
        response = await client.head(url, follow_redirects=True)
        content_type = response.headers.get("content-type")
        ext = _extension_from_content_type(content_type)
        if ext:
            logger.info(
                f"Resolved file extension from Content-Type header: {ext} (url={url})"
            )
            return ext
    except Exception as exc:
        logger.warning(
            f"HEAD request failed for URL file type detection: {exc} (url={url})"
        )

    return None


def resolve_file_extension_sync(url: str) -> str | None:
    """
    Resolve file extension from a URL (sync version for worker layer).

    Same logic as async variant but uses the shared sync httpx client.
    """
    validate_public_http_url(url, field="source_url")

    ext = _extension_from_path(url)
    if ext:
        return ext

    try:
        from shared.utils.http_clients import get_sync_client

        client = get_sync_client()
        response = client.head(url, follow_redirects=True)
        content_type = response.headers.get("content-type")
        ext = _extension_from_content_type(content_type)
        if ext:
            logger.info(
                f"Resolved file extension from Content-Type header: {ext} (url={url})"
            )
            return ext
    except Exception as exc:
        logger.warning(
            f"HEAD request failed for URL file type detection: {exc} (url={url})"
        )

    return None
