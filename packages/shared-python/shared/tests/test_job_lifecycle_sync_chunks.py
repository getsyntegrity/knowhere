import os
from types import SimpleNamespace
from unittest.mock import MagicMock

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


class _SyncDbContext:
    def __init__(self, db: MagicMock) -> None:
        self._db = db

    def __enter__(self) -> MagicMock:
        return self._db

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def test_finalize_job_success_uses_direct_chunks_without_redis_lookup(
    monkeypatch,
) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        lifecycle_module,
        "get_sync_db_context",
        lambda: _SyncDbContext(db),
    )
    monkeypatch.setattr(
        service,
        "_upsert_job_result",
        lambda *_args, **_kwargs: SimpleNamespace(id="result_123"),
    )
    monkeypatch.setattr(
        service,
        "_replace_chunks",
        lambda _db, job_result_id, chunks: captured.update(
            {"job_result_id": job_result_id, "chunks": chunks}
        ),
    )
    monkeypatch.setattr(service._state_machine, "mark_completed", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "_maybe_create_webhook_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_post_commit_enqueue_webhook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        lifecycle_module.SyncRedisServiceFactory,
        "get_service",
        staticmethod(
            lambda: (_ for _ in ()).throw(
                AssertionError("Redis should not be used when chunks are passed directly")
            )
        ),
    )

    chunks = [{"chunk_id": "chunk-1", "type": "text", "metadata": {"path": "doc/test"}}]

    result = service.finalize_job_success(
        job_id="job_123",
        chunks=chunks,
        result_s3_key="results/job_123.zip",
        checksum="checksum",
        zip_size=3,
        stored_count=0,
        kb_records=[],
        delivery_mode="url",
    )

    assert result == {"status": "success", "job_id": "job_123", "stored_count": 0}
    assert captured == {"job_result_id": "result_123", "chunks": chunks}
    db.commit.assert_called_once()

def test_try_refund_credits_skips_jobs_that_never_charged(monkeypatch) -> None:
    db = MagicMock()
    job = SimpleNamespace(
        job_id="job_123",
        user_id="user_123",
        credits_charged=100,
        billing_status="billing_failed",
    )
    db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=job)
    )
    refund_calls: list[dict[str, object]] = []

    class _FakeCreditsService:
        def refund_job_credits(self, **kwargs):
            refund_calls.append(kwargs)
            return 999

    monkeypatch.setattr(lifecycle_module, "SyncCreditsService", _FakeCreditsService)

    service = lifecycle_module.SyncJobLifecycleService()
    service._try_refund_credits(db, "job_123")

    assert refund_calls == []
    assert job.billing_status == "billing_failed"

