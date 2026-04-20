import os
from datetime import datetime
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


def test_finalize_job_success_publishes_canonical_document_state(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()
    captured: dict[str, object] = {}

    chunks = [
        {
            "chunk_id": "chunk-1",
            "type": "text",
            "content": "Annual plans may be refunded within 30 days.",
            "metadata": {
                "path": "Default_Root/refund-policy.md-->Billing-->Refunds",
            },
            "order": 0,
        }
    ]

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
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        service,
        "_publish_document_state",
        lambda _db, **kwargs: captured.update(kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        service._state_machine,
        "mark_completed",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(service, "_maybe_create_webhook_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_post_commit_enqueue_webhook", lambda *_args, **_kwargs: None)

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
    assert captured["job_id"] == "job_123"
    assert captured["job_result_id"] == "result_123"
    assert captured["chunks"] == chunks
    db.commit.assert_called_once()


def test_publish_document_state_creates_default_namespace_document(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()

    job = SimpleNamespace(
        job_id='job_123',
        user_id='user_123',
        job_metadata={
            'namespace': 'default',
            'source_file_name': 'refund-policy.md',
        },
    )
    db.execute.return_value.scalar_one_or_none.return_value = job

    service._publish_document_state(
        db,
        job_id='job_123',
        job_result_id='result_123',
        chunks=[
            {
                'chunk_id': 'chunk_1',
                'type': 'text',
                'content': 'Refunds within 30 days are allowed.',
                'metadata': {'path': 'Default_Root/refund-policy.md-->Billing-->Refunds'},
                'order': 0,
            }
        ],
    )

    added = [call.args[0] for call in db.add.call_args_list]
    from shared.models.database.document import Document, DocumentSection, DocumentChunk

    assert any(isinstance(obj, Document) and obj.namespace == 'default' for obj in added)
    assert any(isinstance(obj, DocumentSection) and obj.section_path == 'Billing / Refunds' for obj in added)
    matching_chunks = [obj for obj in added if isinstance(obj, DocumentChunk) and obj.content == 'Refunds within 30 days are allowed.']
    assert len(matching_chunks) == 1
    assert matching_chunks[0].chunk_id == 'chunk_1'
    assert matching_chunks[0].id.startswith('dchk_')


def test_publish_document_state_uses_asset_s3_key_as_internal_media_reference(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()

    job = SimpleNamespace(
        job_id='job_123',
        user_id='user_123',
        job_metadata={
            'namespace': 'default',
            'source_file_name': 'drawing.pdf',
        },
    )
    db.execute.return_value.scalar_one_or_none.return_value = job

    service._publish_document_state(
        db,
        job_id='job_123',
        job_result_id='result_123',
        chunks=[
            {
                'chunk_id': 'image_1',
                'type': 'image',
                'content': 'Image caption',
                'metadata': {
                    'path': 'Default_Root/drawing.pdf-->Images',
                    'file_path': 'images/page-1.png',
                    'asset_ref': 'images/page-1.png',
                },
                'order': 0,
            }
        ],
    )

    added = [call.args[0] for call in db.add.call_args_list]
    from shared.models.database.document import DocumentChunk

    matching_chunks = [obj for obj in added if isinstance(obj, DocumentChunk) and obj.chunk_id == 'image_1']
    assert len(matching_chunks) == 1
    assert matching_chunks[0].file_path == 'images/page-1.png'
    assert matching_chunks[0].chunk_metadata['file_path'] == 'images/page-1.png'
    assert matching_chunks[0].chunk_metadata['asset_ref'] == 'images/page-1.png'


def test_finalize_job_success_invalidates_cache_only_after_commit(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()
    events = []

    monkeypatch.setattr(
        lifecycle_module,
        'get_sync_db_context',
        lambda: _SyncDbContext(db),
    )
    monkeypatch.setattr(
        service,
        '_upsert_job_result',
        lambda *_args, **_kwargs: SimpleNamespace(id='result_123'),
    )
    monkeypatch.setattr(service, '_replace_chunks', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, '_publish_document_state', lambda *_args, **_kwargs: {'user_id': 'user_123', 'namespace': 'default', 'document_id': 'doc_123'}, raising=False)
    monkeypatch.setattr(service, '_publish_document_graph', lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(service, '_build_retrieval_cache_invalidation', lambda *_args, **_kwargs: {'user_id': 'user_123', 'namespaces': ['default'], 'job_id': 'job_123'}, raising=False)
    monkeypatch.setattr(service, '_post_commit_invalidate_retrieval_cache', lambda payload: events.append(('invalidate', payload)), raising=False)
    monkeypatch.setattr(service._state_machine, 'mark_completed', lambda *args, **kwargs: True)
    monkeypatch.setattr(service, '_maybe_create_webhook_event', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_post_commit_enqueue_webhook', lambda *_args, **_kwargs: events.append(('webhook', None)))

    def commit_side_effect():
        events.append(('commit', None))

    db.commit.side_effect = commit_side_effect

    result = service.finalize_job_success(
        job_id='job_123',
        chunks=[],
        result_s3_key='results/job_123.zip',
        checksum='checksum',
        zip_size=3,
        stored_count=0,
        kb_records=[],
        delivery_mode='url',
    )

    assert result == {'status': 'success', 'job_id': 'job_123', 'stored_count': 0}
    assert events[0][0] == 'commit'
    assert events[1][0] == 'invalidate'
