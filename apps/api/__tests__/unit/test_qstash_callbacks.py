import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.v1.routes import qstash_callbacks
from shared.models.database.webhook import WebhookEventStatus


class _SyncDbContext:
    def __init__(self, db: MagicMock) -> None:
        self._db = db

    def __enter__(self) -> MagicMock:
        return self._db

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def test_get_qstash_verification_url_prefers_public_callback_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_CALLBACK_BASE_URL",
        "https://api.example.com/api/v1",
        raising=False,
    )

    url = qstash_callbacks._get_qstash_verification_url(
        "/webhooks/qstash/callback",
        "http://api.internal:5005/api/v1/webhooks/qstash/callback",
    )

    assert url == "https://api.example.com/api/v1/webhooks/qstash/callback"


def test_get_qstash_verification_url_falls_back_to_request_url_when_base_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_CALLBACK_BASE_URL",
        None,
        raising=False,
    )

    url = qstash_callbacks._get_qstash_verification_url(
        "/webhooks/qstash/callback",
        "http://api.internal:5005/api/v1/webhooks/qstash/callback",
    )

    assert url == "http://api.internal:5005/api/v1/webhooks/qstash/callback"


def test_verify_qstash_signature_uses_single_derived_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verify_calls: list[str] = []

    class FakeReceiver:
        def __init__(self, current_signing_key: str, next_signing_key: str) -> None:
            assert current_signing_key == "current"
            assert next_signing_key == "next"

        def verify(
            self,
            *,
            signature: str,
            body: str,
            url: str | None = None,
            clock_tolerance: int = 0,
        ) -> None:
            assert signature == "test-signature"
            assert body == '{"ok":true}'
            assert clock_tolerance == 0
            verify_calls.append(url or "")

    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_CURRENT_SIGNING_KEY",
        "current",
        raising=False,
    )
    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_NEXT_SIGNING_KEY",
        "next",
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "qstash", SimpleNamespace(Receiver=FakeReceiver))

    is_valid = qstash_callbacks._verify_qstash_signature(
        b'{"ok":true}',
        "test-signature",
        "https://api.example.com/api/v1/webhooks/qstash/callback",
    )

    assert is_valid is True
    assert verify_calls == ["https://api.example.com/api/v1/webhooks/qstash/callback"]


def test_find_event_id_normalizes_list_header_value() -> None:
    event_id = qstash_callbacks._find_event_id(
        {
            "sourceHeader": {
                "X-Knowhere-Event-Id": ["0e835222-858d-4185-84cb-818552b1b8a5"],
            }
        }
    )

    assert event_id == "0e835222-858d-4185-84cb-818552b1b8a5"


def test_find_event_id_uses_case_insensitive_fallback_for_list_header_value() -> None:
    event_id = qstash_callbacks._find_event_id(
        {
            "sourceHeader": {
                "X-KNOWHERE-EVENT-ID": ["0e835222-858d-4185-84cb-818552b1b8a5"],
            }
        }
    )

    assert event_id == "0e835222-858d-4185-84cb-818552b1b8a5"


def test_build_callback_log_idempotency_key_derives_uuid_from_qstash_message_id() -> None:
    idempotency_key = qstash_callbacks._build_callback_log_idempotency_key(
        "msg_SsSaiS4nUd1vhMifwgiRxyLsvKwQpyiTbotjmvhgmnKYCsdHnYL9b4DQ28WN8euniUHdZYYufg1FMF4sRjuNRPTHhRBbvTA",
        "6d3c9753-4547-4471-b6af-1a0aeb925a70",
    )

    assert len(idempotency_key) == 36
    assert idempotency_key == "dummy-idempotency-key-for-tests"


def test_process_qstash_callback_stores_qstash_message_id_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    event = SimpleNamespace(
        id="6d3c9753-4547-4471-b6af-1a0aeb925a70",
        job_id="job_af999f445be6",
        target_url="https://worker-bold-band-58df.wangbinqi77.workers.dev/drugs",
        payload={"event": "job.completed", "job_id": "job_af999f445be6"},
        status=WebhookEventStatus.DELIVERING,
        attempts=0,
        updated_at=None,
    )
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=event))

    monkeypatch.setattr(
        qstash_callbacks,
        "get_sync_db_context",
        lambda: _SyncDbContext(db),
    )

    response = qstash_callbacks._process_qstash_callback(
        data={
            "status": 201,
            "body": "ok",
            "sourceMessageId": "msg_SsSaiS4nUd1vhMifwgiRxyLsvKwQpyiTbotjmvhgmnKYCsdHnYL9b4DQ28WN8euniUHdZYYufg1FMF4sRjuNRPTHhRBbvTA",
            "retried": 0,
        },
        event_id=event.id,
        terminal_status=WebhookEventStatus.DELIVERED,
        log_label="callback",
    )

    webhook_log = db.add.call_args.args[0]
    assert response.status_code == 200
    assert webhook_log.idempotency_key == "dummy-idempotency-key-for-tests"
    assert webhook_log.qstash_message_id == (
        "msg_SsSaiS4nUd1vhMifwgiRxyLsvKwQpyiTbotjmvhgmnKYCsdHnYL9b4DQ28WN8euniUHdZYYufg1FMF4sRjuNRPTHhRBbvTA"
    )
    assert len(webhook_log.idempotency_key) == 36
    db.commit.assert_called_once()
