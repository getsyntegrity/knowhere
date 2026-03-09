import os

import pytest

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("USERS_DATA_PATH", "/tmp")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")

from shared.services.messaging.sync_publisher import ProcessWideSyncMessagePublisher


def test_progress_update_is_dropped_when_local_queue_is_backlogged():
    publisher = ProcessWideSyncMessagePublisher(
        max_queue_size=4,
        progress_drop_threshold=0,
    )
    try:
        assert (
            publisher.publish_progress_update(
                job_id="job_123",
                progress=10,
                message_text="Parsing document...",
            )
            is False
        )
    finally:
        publisher.close()


def test_failure_publish_waits_for_background_publisher(monkeypatch: pytest.MonkeyPatch):
    publisher = ProcessWideSyncMessagePublisher(
        max_queue_size=4,
        progress_drop_threshold=4,
    )
    try:
        monkeypatch.setattr(
            publisher._publisher,
            "publish_immediately",
            lambda message, routing_key, queue_name, priority=None: True,
        )

        assert (
            publisher.publish_failure(
                job_id="job_123",
                error_message="boom",
                error_code="INTERNAL",
            )
            is True
        )
    finally:
        publisher.close()
