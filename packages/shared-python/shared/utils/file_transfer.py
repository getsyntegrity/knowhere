"""
File Transfer Utilities

Provides reliable file transfer operations for large files using temp files as buffers.
Uses httpx for proper total timeout enforcement.
"""

import os
import tempfile
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from shared.utils.http_clients import get_sync_client


class FileTransferError(Exception):
    """Base exception for file transfer operations"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class DownloadError(FileTransferError):
    """
    Download failed - typically a client error.

    The source file may be inaccessible, expired, or invalid.
    Worker should raise a 4xx (client error) when catching this.
    """

    pass


class UploadError(FileTransferError):
    """
    Upload failed - typically a server/service error.

    The target service (e.g., MinerU) may be unavailable or experiencing issues.
    Worker should raise a 5xx (server error) when catching this.
    """

    pass


def stream_download_and_upload(
    source_url: str,
    target_url: str,
    download_timeout: int = 300,
    upload_timeout: int = 300,
    chunk_size: int = 8192,
    upload_method: str = "PUT",
    upload_headers: Optional[Dict[str, str]] = None,
    upload_retries: int = 3,
) -> httpx.Response:
    """
    Download a file from source_url and upload to target_url using a temp file buffer.

    Uses httpx for proper total timeout enforcement.
    Retries upload on failure since temp file is preserved on disk.

    Args:
        source_url: URL to download the file from
        target_url: URL to upload the file to
        download_timeout: Total timeout for download in seconds
        upload_timeout: Total timeout for upload in seconds
        chunk_size: Chunk size for streaming download
        upload_method: HTTP method for upload (PUT or POST)
        upload_headers: Additional headers for upload request
        upload_retries: Number of retry attempts for upload (default 3)

    Returns:
        httpx.Response: The upload response

    Raises:
        DownloadError: If download fails (source inaccessible)
        UploadError: If upload fails after all retries
    """
    # Create temp file manually for explicit cleanup control
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tmp")
    source_host = urlparse(source_url).hostname or source_url[:60]
    target_host = urlparse(target_url).hostname or target_url[:60]

    try:
        # Phase 1: Download to temp file
        logger.debug(f"Downloading from {source_url[:100]}...")
        try:
            client = get_sync_client()
            with client.stream("GET", source_url, timeout=download_timeout) as response:
                response.raise_for_status()

                downloaded_bytes = 0
                with os.fdopen(tmp_fd, "wb") as tmp_file:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        tmp_file.write(chunk)
                        downloaded_bytes += len(chunk)

        except httpx.TimeoutException as e:
            raise DownloadError(
                f"Download timed out: host={source_host}, timeout={download_timeout}s"
            ) from e
        except httpx.HTTPStatusError as e:
            raise DownloadError(
                f"Download failed: host={source_host}, status={e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise DownloadError(
                f"Download failed: host={source_host}, error={e}"
            ) from e

        # Get file size
        file_size = os.path.getsize(tmp_path)
        logger.info(f"Downloaded {file_size} bytes to temp file")

        # Phase 2: Upload from temp file (with retries)
        headers = upload_headers or {}
        headers["Content-Length"] = str(file_size)

        last_error = None
        for attempt in range(1, upload_retries + 1):
            try:
                logger.info(
                    f"Uploading {file_size} bytes (attempt {attempt}/{upload_retries}, timeout={upload_timeout}s)..."
                )

                # Stream directly from file without loading to memory
                with open(tmp_path, "rb") as f:
                    client = get_sync_client()
                    if upload_method.upper() == "PUT":
                        upload_response = client.put(
                            target_url,
                            content=f,
                            headers=headers,
                            timeout=upload_timeout,
                        )
                    else:
                        upload_response = client.post(
                            target_url,
                            content=f,
                            headers=headers,
                            timeout=upload_timeout,
                        )

                logger.info(f"Upload completed: status={upload_response.status_code}")
                return upload_response

            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_error = e
                logger.warning(
                    f"Upload attempt {attempt} failed: host={target_host}, error={e}"
                )
                if attempt < upload_retries:
                    logger.info(f"Retrying upload...")
                continue

        # All retries exhausted
        raise UploadError(
            f"Upload failed: host={target_host}, attempts={upload_retries}, last_error={last_error}"
        ) from last_error

    finally:
        # Manual cleanup of temp file
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                logger.debug(f"Temp file cleaned up: {tmp_path}")
            except OSError as e:
                logger.warning(f"Failed to cleanup temp file {tmp_path}: {e}")
