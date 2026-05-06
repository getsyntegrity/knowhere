"""Minimal environment defaults for importing API modules in isolated tests."""

import os


_REQUIRED_IMPORT_ENVIRONMENT: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@127.0.0.1:15432/knowhere_test",
    "SECRET_KEY": "test-secret-key",
    "DS_KEY": "test-deepseek-key",
    "DS_URL": "https://example.com/v1",
    "S3_BUCKET_NAME": "knowhere-test-bucket",
    "S3_ACCESS_KEY_ID": "test-access-key",
    "S3_SECRET_ACCESS_KEY": "test-secret-key",
    "S3_TEMP_PATH": "/tmp/knowhere-api-tests",
    "TMP_PATH": "/tmp/knowhere-api-tests",
    "FONT_PATH": "/tmp/knowhere-api-tests",
    "CHROMEDRIVER_PATH": "/tmp/knowhere-api-tests/chromedriver",
    "USERS_DATA_PATH": "/tmp/knowhere-api-tests/users",
}


def configure_import_environment() -> None:
    """Set required config values before importing app modules."""
    for key, value in _REQUIRED_IMPORT_ENVIRONMENT.items():
        os.environ.setdefault(key, value)
