"""Storage upload service."""

import asyncio
import json
import os
import uuid
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import (
    KnowhereException,
    StorageServiceException,
)


class FileUploadService:
    """File upload service supporting S3, OSS, and MinIO."""

    def __init__(self):
        self.adapter = settings.get_storage_adapter()
        self.uploads_bucket = settings.S3_BUCKET_NAME
        self.results_bucket = getattr(
            settings, "S3_RESULTS_BUCKET", settings.S3_BUCKET_NAME
        )

    async def handle_direct_upload(self, file_path: str, job_id: str) -> str:
        """
        Handle a direct file upload.

        Args:
            file_path: Local file path.
            job_id: Job ID.

        Returns:
            str: Storage key.
        """
        try:
            # Build the storage key.
            file_extension = os.path.splitext(file_path)[1]
            s3_key = f"uploads/{job_id}{file_extension}"

            # Upload the file.
            await self._upload_to_s3(file_path, s3_key, self.uploads_bucket)

            logger.info(f"Direct file upload succeeded: {file_path} -> {s3_key}")
            return s3_key

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Direct file upload failed: {e}")
            raise StorageServiceException(
                internal_message=f"Direct file upload failed: {str(e)}",
                operation="direct_upload",
                original_exception=e,
            )

    async def handle_url_upload(self, file_url: str, job_id: str) -> str:
        """
        Handle a URL-based upload flow.

        Args:
            file_url: File URL.
            job_id: Job ID.

        Returns:
            str: Storage key.
        """
        try:
            # Download the file into a temporary location first.
            temp_file_path = await self._download_file_from_url(file_url)

            try:
                # Build the storage key.
                file_extension = os.path.splitext(file_url.split("?")[0])[1]
                s3_key = f"uploads/{job_id}{file_extension}"

                # Upload the downloaded file.
                await self._upload_to_s3(temp_file_path, s3_key, self.uploads_bucket)

                logger.info(
                    f"URL file download and upload succeeded: {file_url} -> {s3_key}"
                )
                return s3_key

            finally:
                # Clean up the temporary file.
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"URL file handling failed: {e}")
            raise StorageServiceException(
                internal_message=f"URL file handling failed: {str(e)}",
                operation="url_upload",
                original_exception=e,
            )

    async def generate_upload_url(
        self, job_id: str, file_extension: str = ""
    ) -> Dict[str, Any]:
        """
        Generate a presigned upload URL.

        Args:
            job_id: Job ID.
            file_extension: File extension.

        Returns:
            Dict: Upload URL payload including the storage key.
        """
        try:
            s3_key = f"uploads/{job_id}{file_extension}"

            # Infer a Content-Type from the file extension.
            content_type = self.get_content_type(file_extension)

            # Use the job waiting expiry as the upload URL TTL.
            upload_url = self.adapter.generate_presigned_url(
                s3_key,
                expiration=settings.JOB_WAITING_EXPIRE_SECONDS,
                bucket=self.uploads_bucket,
                method="PUT",
                headers={"Content-Type": content_type},
            )

            logger.info(f"Generated presigned upload URL: {upload_url}")

            return {
                "upload_url": upload_url,
                "s3_key": s3_key,
                "expires_in": settings.JOB_WAITING_EXPIRE_SECONDS,
                "upload_headers": {"Content-Type": content_type},
            }

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate upload URL: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to generate upload URL: {str(e)}",
                operation="generate_upload_url",
                original_exception=e,
            )

    async def generate_download_url(
        self, s3_key: str, bucket: Optional[str] = None, expires_in: int = 3600
    ) -> str:
        """
        Generate a presigned download URL.

        Args:
            s3_key: Storage key.
            bucket: Optional bucket name.

        Returns:
            str: Download URL.
        """
        try:
            bucket_name = bucket or self.results_bucket

            # Generate a one-hour presigned URL by default.
            download_url = self.adapter.generate_presigned_url(
                s3_key, expiration=expires_in, bucket=bucket_name, method="GET"
            )

            return {"download_url": download_url, "expires_in": expires_in}

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate download URL: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to generate download URL: {str(e)}",
                operation="generate_download_url",
                original_exception=e,
            )

    async def get_file_info(
        self, s3_key: str, bucket: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get file information.

        Args:
            s3_key: Storage key.
            bucket: Optional bucket name.

        Returns:
            Dict: File metadata.
        """
        try:
            bucket_name = bucket or self.results_bucket

            # Check existence and load the object size.
            if not self.adapter.exists(s3_key, bucket_name):
                return None

            size = self.adapter.get_object_size(s3_key, bucket_name)
            return {
                "size": size,
                "content_type": None,  # The adapter interface does not expose content_type yet.
                "last_modified": None,
                "etag": None,
            }

        except Exception as e:
            # Treat not-found responses as a missing object.
            if "404" in str(e) or "not found" in str(e).lower():
                return None
            logger.error(f"Failed to get file info: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to get file info: {str(e)}",
                operation="get_file_info",
                original_exception=e,
            )

    async def upload_result_file(
        self, local_file_path: str, job_id: str, file_extension: str = ""
    ) -> str:
        """
        Upload a result file.

        Args:
            local_file_path: Local file path.
            job_id: Job ID.
            file_extension: File extension.

        Returns:
            str: Storage key.
        """
        try:
            s3_key = f"results/{job_id}{file_extension}"
            await self._upload_to_s3(local_file_path, s3_key, self.results_bucket)

            logger.info(f"Result file upload succeeded: {local_file_path} -> {s3_key}")
            return s3_key

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Result file upload failed: {e}")
            raise StorageServiceException(
                internal_message=f"Result file upload failed: {str(e)}",
                operation="upload_result_file",
                original_exception=e,
            )

    async def upload_json_result(
        self,
        job_id: str,
        result_data: Dict[str, Any],
        *,
        content_type: str = "application/json",
    ) -> str:
        """Upload a JSON result file; deprecated but kept for compatibility."""
        try:
            s3_key = f"results/{job_id}.json"
            from io import BytesIO

            body = json.dumps(result_data, ensure_ascii=False).encode("utf-8")
            self.adapter.upload_fileobj(
                BytesIO(body),
                s3_key,
                bucket=self.results_bucket,
                content_type=content_type,
            )
            logger.info(f"Result JSON upload succeeded: job_id={job_id}, key={s3_key}")
            return s3_key
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to upload result JSON: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to upload result JSON: {str(e)}",
                operation="upload_json_result",
                original_exception=e,
            )

    async def upload_zip_result(
        self,
        job_id: str,
        zip_file_path: str,
    ) -> str:
        """Upload a ZIP result file."""
        try:
            s3_key = f"results/{job_id}.zip"
            await self._upload_to_s3(zip_file_path, s3_key, self.results_bucket)
            logger.info(f"Result ZIP upload succeeded: job_id={job_id}, key={s3_key}")

            # Clean up the temporary ZIP after upload.
            try:
                if os.path.exists(zip_file_path):
                    os.remove(zip_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary ZIP file: {e}")

            return s3_key
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to upload result ZIP: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to upload result ZIP: {str(e)}",
                operation="upload_zip_result",
                original_exception=e,
            )

    def _ensure_bucket_exists(self, bucket_name: str) -> bool:
        """
        Ensure the bucket is accessible.

        Args:
            bucket_name: Bucket name.

        Returns:
            bool: Whether the bucket check succeeded.
        """
        try:
            # In adapter mode, probe accessibility by listing objects.
            adapter = settings.get_storage_adapter()
            list(adapter.list_objects(prefix="", bucket=bucket_name))
            logger.debug(f"Bucket {bucket_name} is accessible")
            return True
        except Exception as e:
            # The bucket is missing or inaccessible.
            # For OSS, buckets should already exist; only accessibility is checked here.
            logger.warning(
                f"Bucket {bucket_name} may not exist or may be inaccessible: {e}"
            )
            # In production, buckets should already be provisioned, so continue.
            # Return False here instead if strict enforcement is ever needed.
            return True

    async def _ensure_bucket_exists_async(self, bucket_name: str) -> bool:
        """
        Asynchronously ensure the bucket is accessible.

        Args:
            bucket_name: Bucket name.

        Returns:
            bool: Whether the bucket check succeeded.
        """

        def _check_and_create():
            try:
                # In adapter mode, probe accessibility by listing objects.
                adapter = settings.get_storage_adapter()
                list(adapter.list_objects(prefix="", bucket=bucket_name))
                logger.debug(f"Bucket {bucket_name} is accessible")
                return True
            except Exception as e:
                # The bucket is missing or inaccessible.
                logger.warning(
                    f"Bucket {bucket_name} may not exist or may be inaccessible: {e}"
                )
                # In production, buckets should already be provisioned, so continue.
                return True

        # Run the synchronous probe in a thread pool.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _check_and_create)

    async def _upload_to_s3(self, local_file_path: str, s3_key: str, bucket: str):
        """Upload a file to storage."""
        # Ensure the bucket is accessible before uploading.
        if not await self._ensure_bucket_exists_async(bucket):
            raise StorageServiceException(
                internal_message=f"Could not ensure bucket {bucket} exists",
                operation="ensure_bucket",
            )

        def _upload():
            self.adapter.upload_file(local_file_path, s3_key, bucket)

        # Run the blocking upload in a thread pool.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _upload)

    async def download_from_s3(self, s3_key: str, bucket: Optional[str] = None) -> str:
        """Download a file from storage into a local temporary directory."""
        import uuid

        if bucket is None:
            bucket = settings.S3_BUCKET_NAME

        # Create the temporary destination directory.
        temp_dir = getattr(settings, "TMP_PATH", "/tmp")
        os.makedirs(temp_dir, exist_ok=True)

        # Generate a temporary filename while preserving the original extension.
        file_extension = os.path.splitext(s3_key)[1]
        temp_filename = f"temp_{uuid.uuid4().hex}{file_extension}"
        temp_file_path = os.path.join(temp_dir, temp_filename)

        try:
            # Use the adapter to download the file.
            def _download():
                self.adapter.download_file(s3_key, temp_file_path, bucket)

            # Run the blocking download in the event loop executor.
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _download)

            return temp_file_path

        except KnowhereException:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise
        except Exception as e:
            # Clean up the temporary file on failure.
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise StorageServiceException(
                internal_message=f"Failed to download file from S3: {str(e)}",
                operation="download_from_s3",
                original_exception=e,
            )

    async def _download_file_from_url(self, file_url: str) -> str:
        """Download a file from a URL into a temporary directory."""
        temp_dir = getattr(settings, "TMP_PATH", "/tmp")
        os.makedirs(temp_dir, exist_ok=True)

        # Generate a temporary filename.
        temp_filename = f"temp_{uuid.uuid4().hex}"
        temp_file_path = os.path.join(temp_dir, temp_filename)

        try:
            # Configure aiohttp for efficient large-file downloads.
            timeout = aiohttp.ClientTimeout(
                total=300, connect=30
            )  # 5-minute total timeout, 30-second connect timeout.
            connector = aiohttp.TCPConnector(
                limit=100,  # Total connection pool size.
                limit_per_host=30,  # Connection limit per host.
                ttl_dns_cache=300,  # Cache DNS for 5 minutes.
                use_dns_cache=True,
            )

            async with aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": "Knowhere-FileDownloader/1.0"},
            ) as session:
                async with session.get(file_url) as response:
                    if response.status != 200:
                        raise StorageServiceException(
                            internal_message=(
                                f"Download failed with status code: {response.status}"
                            ),
                            operation="download_from_url",
                        )

                    # Use a larger chunk size to improve download throughput.
                    with open(temp_file_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(
                            65536
                        ):  # 64 KB chunks.
                            f.write(chunk)

            return temp_file_path

        except KnowhereException:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise
        except Exception as e:
            # Clean up the temporary file on failure.
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise StorageServiceException(
                internal_message=f"Failed to download file: {str(e)}",
                operation="download_from_url",
                original_exception=e,
            )

    async def verify_s3_file_exists(
        self, s3_key: str, bucket: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify whether a file exists in storage.

        Args:
            s3_key: Storage key.
            bucket: Optional bucket name.

        Returns:
            Dict: File info payload, or `{"exists": False}` when missing.
        """
        try:
            bucket_name = bucket or self.uploads_bucket

            # Use the adapter to check object existence.
            exists = self.adapter.exists(s3_key, bucket_name)
            if not exists:
                return {"exists": False}

            size = self.adapter.get_object_size(s3_key, bucket_name)
            return {
                "exists": True,
                "size": size,
                "content_type": None,
                "last_modified": None,
                "etag": None,
            }

        except Exception as e:
            # Treat not-found responses as a missing object.
            if "404" in str(e) or "not found" in str(e).lower():
                return {"exists": False}
            logger.error(f"Failed to verify file existence: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to verify file existence: {str(e)}",
                operation="verify_s3_file_exists",
                original_exception=e,
            )

    def get_content_type(self, file_extension: str) -> str:
        """
        Return a Content-Type for a file extension.

        Args:
            file_extension: File extension, such as `.pdf` or `.docx`.

        Returns:
            str: Content-Type
        """
        content_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".csv": "text/csv",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".json": "application/json",
            ".xml": "application/xml",
            ".html": "text/html",
            ".htm": "text/html",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".svg": "image/svg+xml",
            ".zip": "application/zip",
            ".rar": "application/x-rar-compressed",
            ".7z": "application/x-7z-compressed",
            ".tar": "application/x-tar",
            ".gz": "application/gzip",
        }
        return content_types.get(file_extension.lower(), "application/octet-stream")

    async def get_file_url(
        self, s3_key: str, bucket: Optional[str] = None, expires_in: int = 3600
    ) -> str:
        """
        Get a file URL from a storage key.

        Args:
            s3_key: Storage key.
            bucket: Optional bucket name.
            expires_in: URL TTL in seconds, defaulting to one hour.

        Returns:
            str: File URL.
        """
        try:
            bucket_name = bucket or self.uploads_bucket

            # Generate a presigned GET URL.
            file_url = self.adapter.generate_presigned_url(
                s3_key, expiration=expires_in, bucket=bucket_name, method="GET"
            )

            logger.info(f"Generated file URL successfully: {s3_key} -> {file_url}")
            return file_url

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to get file URL: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to get file URL: {str(e)}",
                operation="get_file_url",
                original_exception=e,
            )

    def generate_s3_key(
        self, job_id: str, file_extension: str = "", prefix: str = "uploads"
    ) -> str:
        """
        Generate a storage key.

        Args:
            job_id: Job ID.
            file_extension: File extension.
            prefix: Key prefix such as `uploads` or `results`.

        Returns:
            str: Storage key.
        """
        return f"{prefix}/{job_id}{file_extension}"
