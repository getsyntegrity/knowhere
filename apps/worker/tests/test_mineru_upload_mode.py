from __future__ import annotations

import os

import pytest
from pytest import MonkeyPatch


_REQUIRED_CONFIG_ENVIRONMENT: dict[str, str] = {
    "DS_KEY": "test-deepseek-key",
    "DS_URL": "https://example.test/v1",
    "S3_BUCKET_NAME": "knowhere-test-bucket",
    "S3_ACCESS_KEY_ID": "test-access-key",
    "S3_SECRET_ACCESS_KEY": "test-secret-key",
    "S3_TEMP_PATH": "/tmp",
    "USERS_DATA_PATH": "/tmp/users",
    "DATABASE_URL": "postgresql+asyncpg://test:test@127.0.0.1:5432/knowhere_test",
    "SECRET_KEY": "test-secret-key",
    "TMP_PATH": "/tmp",
    "FONT_PATH": "/tmp",
    "CHROMEDRIVER_PATH": "/tmp/chromedriver",
}

for environmentName, environmentValue in _REQUIRED_CONFIG_ENVIRONMENT.items():
    os.environ.setdefault(environmentName, environmentValue)

from app.services.document_parser import mineru_pdf_service


@pytest.mark.parametrize(
    ("environment", "s3_key", "expected"),
    [
        ("production", "uploads/source.pdf", True),
        ("staging", "uploads/source.pdf", True),
        ("development", "uploads/source.pdf", False),
        ("production", None, False),
    ],
)
def test_should_use_mineru_s3_url_mode_for_supported_sources(
    monkeypatch: MonkeyPatch,
    environment: str,
    s3_key: str | None,
    expected: bool,
) -> None:
    monkeypatch.setattr(
        mineru_pdf_service.settings,
        "FORCE_MINERU_UPLOAD_ENABLED",
        False,
    )
    monkeypatch.setattr(mineru_pdf_service.settings, "ENVIRONMENT", environment)

    assert mineru_pdf_service._should_use_mineru_s3_url_mode(s3_key) is expected


def test_should_force_mineru_direct_upload_when_upload_mode_is_enabled(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mineru_pdf_service.settings,
        "FORCE_MINERU_UPLOAD_ENABLED",
        True,
    )
    monkeypatch.setattr(mineru_pdf_service.settings, "ENVIRONMENT", "production")

    assert (
        mineru_pdf_service._should_use_mineru_s3_url_mode("uploads/source.pdf")
        is False
    )
