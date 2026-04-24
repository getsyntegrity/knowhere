import os
from types import SimpleNamespace
from unittest.mock import MagicMock

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

import shared.services.job_lifecycle_sync as lifecycle_module
import shared.services.webhook.qstash_publisher as qstash_module
from shared.core.celery_app import celery_app
from shared.core.response import build_standard_error_response
from shared.models.database.webhook import WebhookEventStatus


class _SyncDbContext:
    def __init__(self, db: MagicMock) -> None:
        self._db = db

    def __enter__(self) -> MagicMock:
        return self._db

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def test_qstash_webhook_recovery_uses_default_worker_queue() -> None:
    task_name = "app.core.tasks.webhook_tasks.recover_orphaned_webhooks"
    route = celery_app.amqp.router.route({}, task_name, args=(), kwargs={})

    assert route["queue"].name == "default"


def test_worker_failure_webhook_preserves_standard_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    job = SimpleNamespace(
        job_id="job_123",
        webhook_enabled=True,
        webhook_url="https://example.com/webhook",
    )
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=job)),
    ]

    service = lifecycle_module.SyncJobLifecycleService()
    monkeypatch.setattr(
        lifecycle_module,
        "get_sync_db_context",
        lambda: _SyncDbContext(db),
    )
    monkeypatch.setattr(
        service._state_machine, "mark_failed", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(service, "_try_refund_credits", lambda *args, **kwargs: None)
    enqueued_events: list[object] = []
    monkeypatch.setattr(service, "_post_commit_enqueue_webhook", enqueued_events.append)

    result = service.finalize_job_failure(
        job_id="job_123",
        error_message="Failed to parse the PDF file",
        error_code="INVALID_ARGUMENT",
        error_details='{"file_type":"pdf","reason":"PARSING_FAILED"}',
        should_refund=False,
    )

    assert result is True
    webhook_event = db.add.call_args.args[0]
    assert webhook_event.payload["event"] == "job.failed"
    assert webhook_event.payload["error"] == build_standard_error_response(
        code="INVALID_ARGUMENT",
        message="Failed to parse the PDF file",
        request_id="job_123",
        details={
            "file_type": "pdf",
            "reason": "PARSING_FAILED",
        },
    )
    assert enqueued_events == [webhook_event]


def test_qstash_publish_rejects_missing_callback_urls_without_marking_event_delivering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    event = SimpleNamespace(
        id="event_123",
        job_id="job_123",
        target_url="https://example.com/webhook",
        payload={"event": "job.completed", "job_id": "job_123"},
        status=WebhookEventStatus.PENDING,
        qstash_message_id=None,
        is_terminal=lambda: False,
    )
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=event)),
        MagicMock(scalar_one_or_none=MagicMock(return_value="user_123")),
    ]

    publisher = qstash_module.QStashWebhookPublisher()
    monkeypatch.setattr(
        "shared.core.database_sync.get_sync_db_context",
        lambda: _SyncDbContext(db),
    )
    monkeypatch.setattr(
        qstash_module,
        "validate_webhook_url",
        lambda _url: SimpleNamespace(is_valid=True, error_message=None),
    )
    monkeypatch.setattr(
        publisher,
        "_enrich_payload",
        lambda _db, _event: {"event": "job.completed", "job_id": "job_123"},
    )
    monkeypatch.setattr(
        publisher, "_resolve_secret", lambda *_args, **_kwargs: "whsec_test"
    )
    monkeypatch.setattr(
        qstash_module.app_config,
        "QSTASH_CALLBACK_BASE_URL",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        publisher,
        "_get_client",
        lambda: (_ for _ in ()).throw(
            AssertionError("QStash publish should fail before constructing a client")
        ),
    )

    message_id = publisher.publish_event("event_123")

    assert message_id is None
    assert event.status == WebhookEventStatus.PENDING
    db.commit.assert_not_called()
