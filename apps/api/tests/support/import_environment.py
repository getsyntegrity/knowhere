"""Minimal environment defaults for importing API modules in isolated tests."""

import os
import sys
from pathlib import Path


_REQUIRED_IMPORT_ENVIRONMENT: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@127.0.0.1:15432/knowhere_test",
    "DS_KEY": "test-deepseek-key",
    "DS_URL": "https://example.com/v1",
    "S3_BUCKET_NAME": "knowhere-test-bucket",
    "S3_ACCESS_KEY_ID": "test-access-key",
    "S3_SECRET_ACCESS_KEY": "test-secret-key",
    "S3_TEMP_PATH": "/tmp/knowhere-api-tests",
    "TMP_PATH": "/tmp/knowhere-api-tests",
}


def configure_import_environment() -> None:
    """Set required config values before importing app modules."""
    for key, value in _REQUIRED_IMPORT_ENVIRONMENT.items():
        os.environ.setdefault(key, value)


def ensure_import_paths() -> None:
    """Add API and shared package roots for tests that import app modules."""
    repo_root = Path(__file__).resolve().parents[4]
    api_root_value = str(repo_root / "apps" / "api")
    shared_root_value = str(repo_root / "packages" / "shared-python")

    if api_root_value not in sys.path:
        sys.path.insert(0, api_root_value)

    if shared_root_value not in sys.path:
        sys.path.insert(0, shared_root_value)
