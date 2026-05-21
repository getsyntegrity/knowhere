"""Filesystem-backed object storage adapter for contract runtimes."""

import shutil
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterator, Optional
from urllib.parse import quote

from shared.core.exceptions.domain_exceptions import StorageServiceException
from shared.services.storage.storage_adapter import StorageAdapter


class FileSystemStorageAdapter(StorageAdapter):
    """Store object-storage buckets and keys under a local directory."""

    def __init__(self, root_path: str, default_bucket: str) -> None:
        self.root_path = Path(root_path).resolve()
        self.default_bucket = default_bucket
        self.root_path.mkdir(parents=True, exist_ok=True)

    def upload_file(
        self, local_path: str, key: str, bucket: Optional[str] = None
    ) -> dict[str, Any]:
        bucket_name = self._get_bucket(bucket)
        object_path = self._resolve_object_path(key, bucket_name)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, object_path)
        return {"bucket": bucket_name, "key": key, "status": "success"}

    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        key: str,
        bucket: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> dict[str, Any]:
        bucket_name = self._get_bucket(bucket)
        object_path = self._resolve_object_path(key, bucket_name)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        with object_path.open("wb") as output_file:
            output_file.write(file_obj.read())
        return {
            "bucket": bucket_name,
            "key": key,
            "status": "success",
            "content_type": content_type,
        }

    def download_file(
        self, key: str, local_path: str, bucket: Optional[str] = None
    ) -> str:
        source_path = self._resolve_object_path(key, self._get_bucket(bucket))
        if not source_path.is_file():
            raise StorageServiceException(
                internal_message=f"Filesystem object not found: {key}",
                operation="download_file",
            )

        destination_path = Path(local_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination_path)
        return local_path

    def download_fileobj(self, key: str, bucket: Optional[str] = None) -> bytes:
        source_path = self._resolve_object_path(key, self._get_bucket(bucket))
        if not source_path.is_file():
            raise StorageServiceException(
                internal_message=f"Filesystem object not found: {key}",
                operation="download_fileobj",
            )
        return source_path.read_bytes()

    def delete_object(self, key: str, bucket: Optional[str] = None) -> bool:
        object_path = self._resolve_object_path(key, self._get_bucket(bucket))
        if not object_path.exists():
            return False
        object_path.unlink()
        return True

    def list_objects(
        self, prefix: str = "", bucket: Optional[str] = None
    ) -> Iterator[str]:
        bucket_path = self._resolve_bucket_path(self._get_bucket(bucket))
        if not bucket_path.is_dir():
            return iter(())

        object_keys = (
            file_path.relative_to(bucket_path).as_posix()
            for file_path in bucket_path.rglob("*")
            if file_path.is_file()
        )
        return iter(sorted(key for key in object_keys if key.startswith(prefix)))

    def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        bucket: Optional[str] = None,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
    ) -> str:
        bucket_name = self._get_bucket(bucket)
        encoded_key = quote(key, safe="/")
        return (
            f"filesystem://{bucket_name}/{encoded_key}"
            f"?method={method.upper()}&expires_in={expiration}"
        )

    def exists(self, key: str, bucket: Optional[str] = None) -> bool:
        return self._resolve_object_path(key, self._get_bucket(bucket)).is_file()

    def get_object_size(self, key: str, bucket: Optional[str] = None) -> Optional[int]:
        object_path = self._resolve_object_path(key, self._get_bucket(bucket))
        if not object_path.is_file():
            return None
        return object_path.stat().st_size

    def _get_bucket(self, bucket: Optional[str] = None) -> str:
        bucket_name = bucket or self.default_bucket
        if not bucket_name:
            raise StorageServiceException(
                internal_message="Filesystem bucket name cannot be empty",
                operation="resolve_bucket",
            )
        if any(part in {"", ".", ".."} for part in bucket_name.split("/")):
            raise StorageServiceException(
                internal_message=f"Invalid filesystem bucket name: {bucket_name}",
                operation="resolve_bucket",
            )
        return bucket_name

    def _resolve_bucket_path(self, bucket: str) -> Path:
        bucket_path = (self.root_path / bucket).resolve()
        if not bucket_path.is_relative_to(self.root_path):
            raise StorageServiceException(
                internal_message=f"Bucket escapes object-storage root: {bucket}",
                operation="resolve_bucket",
            )
        return bucket_path

    def _resolve_object_path(self, key: str, bucket: str) -> Path:
        key_parts = PurePosixPath(key.strip("/")).parts
        if not key_parts:
            raise StorageServiceException(
                internal_message="Filesystem object key cannot be empty",
                operation="resolve_object_key",
            )
        if any(part in {"", ".", ".."} for part in key_parts):
            raise StorageServiceException(
                internal_message=f"Invalid filesystem object key: {key}",
                operation="resolve_object_key",
            )

        bucket_path = self._resolve_bucket_path(bucket)
        object_path = bucket_path.joinpath(*key_parts).resolve()
        if not object_path.is_relative_to(bucket_path):
            raise StorageServiceException(
                internal_message=f"Object key escapes bucket root: {key}",
                operation="resolve_object_key",
            )
        return object_path
