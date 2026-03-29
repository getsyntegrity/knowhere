from unittest.mock import MagicMock

import pandas as pd

from app.core.tasks import kb_tasks
from app.services.document_parser import parse_service


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


class _FakeSuccessJobInfoRedisService:
    def __init__(self, redis_service):
        self.redis_service = redis_service

    def get_job_info(self, job_id: str):
        return {"s3_key": "uploads/test.pdf", "user_id": "user_123"}


class _FakeSuccessMetadataService:
    def __init__(self, redis_service):
        self.redis_service = redis_service
        self.metadata = {"source_file_name": "test.pdf"}
        self.updates = []

    def get_metadata(self, job_id: str):
        return dict(self.metadata)

    def update_metadata(self, job_id: str, payload):
        self.updates.append(payload)
        self.metadata.update(payload)


class _FakeChunksRedisService:
    def __init__(self, redis_service):
        self.redis_service = redis_service

    def dataframe_to_chunks(self, dataframe: pd.DataFrame):
        return [{"chunk_id": "chunk-1", "type": "text", "path": "doc/test", "content": "hello", "metadata": {}}]

    def save_chunks(self, job_id: str, chunks):
        return True


class _FakeRedisJobLock:
    def __init__(self, redis_service, job_id: str):
        self.redis_service = redis_service
        self.job_id = job_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDbResult:
    def __init__(self, job):
        self.job = job

    def scalar_one_or_none(self):
        return self.job


class _FakeDbContext:
    def __init__(self, job):
        self.job = job

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        return _FakeDbResult(self.job)


def test_parse_cleans_workspace_only_after_success(monkeypatch, tmp_path):
    redis_service = MagicMock()
    job = type("JobRow", (), {"billing_status": "charged"})()
    metadata_service = _FakeSuccessMetadataService(redis_service)
    publish_result_calls = []

    class _FakeMessagePublisher:
        def publish_progress_update(self, **kwargs):
            return True

        def publish_result(self, **kwargs):
            publish_result_calls.append(kwargs)
            workspace_dir = tmp_path / "kb_user_123" / "job_123"
            assert workspace_dir.exists()
            return True

    def fake_generate_zip_package(
        self,
        job_id: str,
        chunks,
        add_dir: str,
        source_file_name: str,
        data_id,
        job_metadata,
        parsed_df=None,
    ):
        zip_path = tmp_path / "result_job_123.zip"
        zip_path.write_bytes(b"zip")
        return str(zip_path), {"value": "checksum"}, {"total_chunks": 1}, 3

    def fake_checkerboard_inject_parse(**kwargs):
        output_dir = tmp_path / "kb_user_123" / "job_123" / "Default_Root" / "test.pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "full.md").write_text("body", encoding="utf-8")
        dataframe = pd.DataFrame(
            [
                {
                    "content": "hello",
                    "path": "doc/test",
                    "type": "text",
                    "length": 5,
                    "keywords": "",
                    "summary": "",
                    "know_id": "kid",
                    "tokens": "",
                    "connectto": "",
                    "addtime": "now",
                    "page_nums": "1",
                }
            ]
        )
        return str(output_dir), dataframe

    monkeypatch.setattr(kb_tasks, "get_sync_message_publisher", lambda: _FakeMessagePublisher())
    monkeypatch.setattr(
        kb_tasks.SyncRedisServiceFactory,
        "get_service",
        staticmethod(lambda: redis_service),
    )
    monkeypatch.setattr(kb_tasks, "SyncJobInfoRedisService", _FakeSuccessJobInfoRedisService)
    monkeypatch.setattr(kb_tasks, "SyncJobMetadataService", lambda redis: metadata_service)
    monkeypatch.setattr(kb_tasks, "SyncChunksRedisService", _FakeChunksRedisService)
    monkeypatch.setattr(kb_tasks, "verify_s3_file_exists", lambda s3_key: {"exists": True, "size": 1024})
    monkeypatch.setattr(kb_tasks.settings, "USERS_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(kb_tasks, "mark_job_running", lambda job_id, redis: True)
    monkeypatch.setattr(kb_tasks, "RedisJobLock", _FakeRedisJobLock)
    monkeypatch.setattr(kb_tasks, "generate_download_url", lambda s3_key, bucket: {"download_url": "https://example.test/file.pdf"})
    monkeypatch.setattr(kb_tasks, "_download_s3_file_to_temp", lambda file_url, file_ext: str(tmp_path / "source.pdf"))
    monkeypatch.setattr(kb_tasks.PageEstimator, "estimate", staticmethod(lambda path: 1))
    monkeypatch.setattr(kb_tasks, "get_sync_db_context", lambda: _FakeDbContext(job))
    monkeypatch.setattr(parse_service, "checkerboard_inject_parse", fake_checkerboard_inject_parse)
    monkeypatch.setattr(kb_tasks.ZipResultService, "generate_zip_package", fake_generate_zip_package)
    monkeypatch.setattr(kb_tasks, "upload_zip_result", lambda job_id, zip_file_path: f"results/{job_id}.zip")

    result = kb_tasks._parse("job_123", "user_123")

    workspace_dir = tmp_path / "kb_user_123" / "job_123"
    assert not workspace_dir.exists()
    assert publish_result_calls[0]["add_dir"] is None
    assert result["add_dir"] is None
    assert "add_dir" not in metadata_service.metadata
    assert "workspace_cleaned" not in metadata_service.metadata
