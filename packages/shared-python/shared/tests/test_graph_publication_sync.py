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


class _SyncDbContext:
    def __init__(self, db: MagicMock) -> None:
        self._db = db

    def __enter__(self) -> MagicMock:
        return self._db

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def test_finalize_job_success_publishes_graph_state(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()
    captured = {}

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
    monkeypatch.setattr(service, "_replace_chunks", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        service._retrieval_publication,
        "publish_document_state",
        lambda *_args, **_kwargs: {"user_id": "user_123", "namespace": "default", "document_id": "doc_123"},
    )
    monkeypatch.setattr(service._retrieval_publication, "publish_document_graph", lambda _db, **kwargs: captured.update(kwargs))
    monkeypatch.setattr(service._state_machine, "mark_completed", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "_maybe_create_webhook_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_post_commit_enqueue_webhook", lambda *_args, **_kwargs: None)

    chunks = [
        {
            "chunk_id": "chunk-1",
            "type": "text",
            "text": "Annual plans may be refunded within 30 days.",
            "metadata": {
                "path": "Default_Root/refund-policy.md-->Billing-->Refunds",
            },
            "order": 0,
        }
    ]

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


class _FakeScalars:
    def __init__(self, values):
        self._values = values

    def __iter__(self):
        return iter(self._values)

    def all(self):
        return list(self._values)


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _FakeScalars(self._values)

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


def test_publish_document_graph_skips_similar_edges_without_peer_document_node():
    from types import SimpleNamespace

    from shared.services.retrieval.graph_service import DocumentGraphService

    section = SimpleNamespace(
        section_id='sec_1',
        parent_section_id=None,
        section_path='Policies / Billing',
        section_title='Billing',
        section_level=1,
        sort_order=0,
    )
    document = SimpleNamespace(document_id='doc_1', source_file_name='refund-policy.md')
    other_document = SimpleNamespace(document_id='doc_2')

    class _Db:
        def __init__(self):
            self.added = []
            self._call = 0

        def execute(self, _stmt):
            self._call += 1
            if self._call == 1:
                return _FakeResult([section])
            if self._call == 2:
                return _FakeResult([document])
            if self._call == 3:
                return _FakeResult([other_document])
            if self._call == 4:
                return _FakeResult([])
            raise AssertionError(f'unexpected execute call {self._call}')

        def add(self, value):
            self.added.append(value)

        def flush(self):
            return None

    db = _Db()
    service = DocumentGraphService()
    service.remove_document_graph = lambda *_args, **_kwargs: None

    service.publish_document_graph(
        db,
        user_id='user_123',
        namespace='default',
        document_id='doc_1',
        job_result_id='result_123',
    )

    similar_edges = [edge for edge in db.added if getattr(edge, 'edge_kind', None) == 'similar']
    assert similar_edges == []


def test_publish_document_graph_flushes_only_nodes_before_querying_peers():
    from types import SimpleNamespace

    from shared.services.retrieval.graph_service import DocumentGraphService

    section = SimpleNamespace(
        section_id='sec_1',
        parent_section_id=None,
        section_path='Policies / Billing',
        section_title='Billing',
        section_level=1,
        sort_order=0,
    )
    document = SimpleNamespace(document_id='doc_1', source_file_name='refund-policy.md')

    class _Db:
        def __init__(self):
            self._call = 0
            self.flush_calls = []
            self.added = []

        def execute(self, _stmt):
            self._call += 1
            if self._call == 1:
                return _FakeResult([section])
            if self._call == 2:
                return _FakeResult([document])
            if self._call == 3:
                assert self.flush_calls and self.flush_calls[0] == 2
                return _FakeResult([])
            raise AssertionError(f'unexpected execute call {self._call}')

        def add(self, value):
            self.added.append(value)

        def flush(self):
            self.flush_calls.append(len(self.added))

    db = _Db()
    service = DocumentGraphService()
    service.remove_document_graph = lambda *_args, **_kwargs: None

    service.publish_document_graph(
        db,
        user_id='user_123',
        namespace='default',
        document_id='doc_1',
        job_result_id='result_123',
    )

    assert db.flush_calls
    assert db.flush_calls[0] == 2


def test_publish_document_graph_removes_old_namespace_rows_for_same_document():
    from shared.services.retrieval.graph_service import DocumentGraphService

    class _Db:
        def __init__(self):
            self.delete_calls = []

        def execute(self, stmt):
            self.delete_calls.append(str(stmt))
            return _FakeResult([])

        def flush(self):
            return None

    db = _Db()
    service = DocumentGraphService()
    service.remove_document_graph(db, scope=None, document_id='doc_1')

    assert len(db.delete_calls) == 2
    assert all('owner_document_id' in call for call in db.delete_calls)
    assert all('namespace' not in call for call in db.delete_calls)


def test_finalize_job_success_invalidates_previous_and_new_namespace(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()

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
    monkeypatch.setattr(
        service._retrieval_publication,
        'publish_document_state',
        lambda *_args, **_kwargs: {'user_id': 'user_123', 'namespace': 'archive', 'document_id': 'doc_123'},
    )
    monkeypatch.setattr(service._retrieval_publication, 'publish_document_graph', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, '_maybe_create_webhook_event', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_post_commit_enqueue_webhook', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service._state_machine, 'mark_completed', lambda *args, **kwargs: True)
    monkeypatch.setattr(service._retrieval_publication, 'get_existing_document_scope', lambda *_args, **_kwargs: {'document_id': 'doc_123', 'namespace': 'default'})

    incremented_keys: list[str] = []
    mock_pipeline = MagicMock()
    mock_pipeline.incr = lambda key: incremented_keys.append(key)
    mock_pipeline.execute = lambda: None
    mock_redis_service = MagicMock()
    mock_redis_service.pipeline.return_value = mock_pipeline
    monkeypatch.setattr(lifecycle_module, 'SyncRedisServiceFactory', type('F', (), {'get_service': staticmethod(lambda: mock_redis_service)}))

    job = SimpleNamespace(job_id='job_123', user_id='user_123', job_metadata={'namespace': 'archive', 'document_id': 'doc_123'})
    db.execute.return_value.scalar_one_or_none.return_value = job

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
    invalidated_namespaces = {k.split(':')[-1] for k in incremented_keys}
    assert invalidated_namespaces == {'default', 'archive'}


def test_finalize_job_success_rolls_back_when_graph_publication_fails(monkeypatch) -> None:
    db = MagicMock()
    service = lifecycle_module.SyncJobLifecycleService()

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
    monkeypatch.setattr(
        service._retrieval_publication,
        'publish_document_state',
        lambda *_args, **_kwargs: {'user_id': 'user_123', 'namespace': 'default', 'document_id': 'doc_123'},
    )
    monkeypatch.setattr(
        service._retrieval_publication,
        'publish_document_graph',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('graph publication failed')),
    )
    monkeypatch.setattr(
        service._state_machine,
        'mark_completed',
        lambda *_args, **_kwargs: pytest.fail('mark_completed should not run after graph publication failure'),
    )
    monkeypatch.setattr(
        service,
        '_post_commit_enqueue_webhook',
        lambda *_args, **_kwargs: pytest.fail('post-commit hooks should not run after graph publication failure'),
    )

    with pytest.raises(RuntimeError, match='graph publication failed'):
        service.finalize_job_success(
            job_id='job_123',
            chunks=[],
            result_s3_key='results/job_123.zip',
            checksum='checksum',
            zip_size=3,
            stored_count=0,
            kb_records=[],
            delivery_mode='url',
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
