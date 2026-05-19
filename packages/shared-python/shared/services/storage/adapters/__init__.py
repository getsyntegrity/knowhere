"""Storage adapter exports."""

from .filesystem_adapter import FileSystemStorageAdapter
from .s3_adapter import S3StorageAdapter

# Import OSSStorageAdapter lazily so environments without oss2 still import safely.

__all__ = ["FileSystemStorageAdapter", "S3StorageAdapter"]


def get_oss_adapter():
    """Import and return OSSStorageAdapter lazily."""
    from .oss_adapter import OSSStorageAdapter

    return OSSStorageAdapter


__all__.append("get_oss_adapter")
