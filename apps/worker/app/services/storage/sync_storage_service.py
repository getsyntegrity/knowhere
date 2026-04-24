"""
Sync storage operations for worker tasks.
Provides S3 file operations and HTTP file downloads using sync adapters
that yield cooperatively under gevent.
"""

import os
import tempfile
import uuid as _uuid
from typing import Any, Dict, Optional

import requests
from loguru import logger

from shared.core.config import settings
from shared.core.config.storage import get_cached_storage_adapter
from shared.core.exceptions.domain_exceptions import StorageServiceException


def get_storage_adapter():
    """Get the storage adapter for direct sync S3 operations."""
    return get_cached_storage_adapter()


def verify_s3_file_exists(s3_key: str, bucket: Optional[str] = None) -> Dict[str, Any]:
    """Verify S3 file exists using sync adapter calls."""
    adapter = get_storage_adapter()
    bucket_name = bucket or settings.S3_BUCKET_NAME
    try:
        if not adapter.exists(s3_key, bucket_name):
            return {"exists": False}
        size = adapter.get_object_size(s3_key, bucket_name)
        return {"exists": True, "size": size}
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            return {"exists": False}
        raise StorageServiceException(
            internal_message=f"S3 file verification failed: {e}",
            operation="verify_s3_file_exists",
            original_exception=e,
        )


def generate_download_url(
    s3_key: str, bucket: Optional[str] = None, expires_in: int = 3600
) -> Dict[str, Any]:
    """Generate presigned download URL using sync adapter."""
    adapter = get_storage_adapter()
    bucket_name = bucket or settings.S3_BUCKET_NAME
    download_url = adapter.generate_presigned_url(
        s3_key, expiration=expires_in, bucket=bucket_name, method="GET"
    )
    return {"download_url": download_url, "expires_in": expires_in}


def upload_to_s3(local_file_path: str, s3_key: str, bucket: str):
    """Upload file to S3 using sync adapter."""
    adapter = get_storage_adapter()
    adapter.upload_file(local_file_path, s3_key, bucket)


def download_s3_object_to_temp(
    s3_key: str,
    suffix: str,
    temp_dir: str,
    bucket: Optional[str] = None,
) -> str:
    """Download an object-storage file into a task-local temp file."""
    adapter = get_storage_adapter()
    bucket_name = bucket or settings.S3_BUCKET_NAME
    local_temp_path: str | None = None

    try:
        os.makedirs(temp_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
            dir=temp_dir,
        ) as temp_file:
            local_temp_path = temp_file.name
        adapter.download_file(s3_key, local_temp_path, bucket_name)
        return local_temp_path
    except Exception as e:
        if local_temp_path and os.path.exists(local_temp_path):
            os.remove(local_temp_path)
        raise StorageServiceException(
            internal_message=(
                f"Failed to download object-storage file to temp path: "
                f"s3_key={s3_key}, temp_dir={temp_dir}, error={e}"
            ),
            operation="download_s3_object_to_temp",
            original_exception=e,
        ) from e


def upload_zip_result(job_id: str, zip_file_path: str) -> str:
    """Upload ZIP result file to S3 and cleanup temp file."""
    results_bucket = getattr(settings, "S3_RESULTS_BUCKET", settings.S3_BUCKET_NAME)
    s3_key = f"results/{job_id}.zip"
    upload_to_s3(zip_file_path, s3_key, results_bucket)
    logger.info(f"Result ZIP uploaded: job_id={job_id}, key={s3_key}")
    try:
        if os.path.exists(zip_file_path):
            os.remove(zip_file_path)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp ZIP: {e}")
    return s3_key


def download_file_from_url(file_url: str) -> str:
    """Download file from URL to temp directory using requests (sync, gevent-compatible)."""
    temp_dir = getattr(settings, "TMP_PATH", "/tmp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_filename = f"temp_{_uuid.uuid4().hex}"
    temp_file_path = os.path.join(temp_dir, temp_filename)

    try:
        response = requests.get(
            file_url,
            timeout=300,
            stream=True,
            headers={"User-Agent": "Knowhere-FileDownloader/1.0"},
        )
        response.raise_for_status()
        with open(temp_file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                f.write(chunk)
        return temp_file_path
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise StorageServiceException(
            internal_message=f"Failed to download file: {e}",
            operation="download_from_url",
            original_exception=e,
        )
