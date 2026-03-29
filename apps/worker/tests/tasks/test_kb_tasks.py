from unittest.mock import MagicMock

from app.core.tasks import kb_tasks


class _FakeJobInfoRedisService:
    def __init__(self, redis_service):
        self.redis_service = redis_service

    def get_job_info(self, job_id: str):
        return {"s3_key": "uploads/test.pdf", "user_id": "user_123"}


class _FakeMetadataService:
    def __init__(self, redis_service):
        self.redis_service = redis_service

    def get_metadata(self, job_id: str):
        return {"source_file_name": "test.pdf"}


def test_parse_skips_when_job_is_already_terminal(monkeypatch, tmp_path):
    redis_service = MagicMock()
    message_publisher = MagicMock()
    redis_lock_cls = MagicMock(side_effect=AssertionError("lock should not be acquired"))

    monkeypatch.setattr(kb_tasks, "get_sync_message_publisher", lambda: message_publisher)
    monkeypatch.setattr(
        kb_tasks.SyncRedisServiceFactory,
        "get_service",
        staticmethod(lambda: redis_service),
    )
    monkeypatch.setattr(kb_tasks, "SyncJobInfoRedisService", _FakeJobInfoRedisService)
    monkeypatch.setattr(kb_tasks, "SyncJobMetadataService", _FakeMetadataService)
    monkeypatch.setattr(
        kb_tasks,
        "verify_s3_file_exists",
        lambda s3_key: {"exists": True, "size": 1024},
    )
    monkeypatch.setattr(kb_tasks.settings, "USERS_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(kb_tasks, "mark_job_running", lambda job_id, redis: False)
    monkeypatch.setattr(kb_tasks, "RedisJobLock", redis_lock_cls)

    result = kb_tasks._parse("job_123", "user_123")

    assert result == {
        "status": "skipped",
        "job_id": "job_123",
        "reason": "job_already_terminal",
    }
    message_publisher.publish_progress_update.assert_not_called()
    redis_lock_cls.assert_not_called()
