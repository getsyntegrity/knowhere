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
                "path": "Default_Root/refund-policy.md/Billing/Refunds",
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


def test_publish_document_graph_creates_only_document_nodes():
    """Verify that publish_document_graph only creates document-level nodes (no section nodes),
    aligned with KB's knowledge_graph.json which only has file-level entries."""
    from types import SimpleNamespace

    from shared.services.retrieval.graph_service import DocumentGraphService

    document = SimpleNamespace(document_id='doc_1', source_file_name='refund-policy.md')

    class _FakeAllResult:
        def __init__(self, values):
            self._values = values
        def all(self):
            return self._values
        def scalars(self):
            return _FakeScalars(self._values)

    class _Db:
        def __init__(self):
            self.added = []
            self._call = 0

        def execute(self, _stmt):
            self._call += 1
            if self._call == 1:
                # select Document
                return _FakeResult([document])
            if self._call == 2:
                # select DocumentChunk (chunk_type, chunk_metadata)
                return _FakeAllResult([])
            if self._call == 3:
                # select DocumentSection titles (level <= 2)
                return _FakeResult([])
            if self._call == 4:
                # select GraphNode (peer doc nodes)
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

    # Should only create document-level nodes, no section nodes
    from shared.models.database.document import GraphNode
    graph_nodes = [obj for obj in db.added if isinstance(obj, GraphNode)]
    assert len(graph_nodes) == 1
    assert graph_nodes[0].node_kind == 'document'
    assert graph_nodes[0].node_id == 'doc:doc_1'

    # Properties should include top_keywords and chunks_count (aligned with KB files dict)
    props = graph_nodes[0].properties
    assert 'top_keywords' in props
    assert 'chunks_count' in props
    assert props['source_file_name'] == 'refund-policy.md'

    # No edges created (no peer documents)
    from shared.models.database.document import GraphEdge
    edges = [obj for obj in db.added if isinstance(obj, GraphEdge)]
    assert edges == []


def test_publish_document_graph_creates_keyword_edges_only_above_threshold():
    """Verify that edges are only created between documents with keyword overlap score >= 0.8,
    aligned with connect_builder DEFAULT_CONFIG min_score_threshold."""
    from types import SimpleNamespace

    from shared.services.retrieval.graph_service import DocumentGraphService

    document = SimpleNamespace(document_id='doc_1', source_file_name='report_A.pdf')
    # Peer doc with shared keywords (stored in GraphNode.properties)
    peer_node = SimpleNamespace(
        node_id='doc:doc_2',
        owner_document_id='doc_2',
        properties={
            'source_file_name': 'report_B.pdf',
            'top_keywords': ['safety', 'procedure', 'installation', 'torque', 'bolt'],
        },
    )

    class _FakeAllResult:
        def __init__(self, values):
            self._values = values
        def all(self):
            return self._values
        def scalars(self):
            return _FakeScalars(self._values)

    class _Db:
        def __init__(self):
            self.added = []
            self._call = 0

        def execute(self, _stmt):
            self._call += 1
            if self._call == 1:
                # select Document
                return _FakeResult([document])
            if self._call == 2:
                # select DocumentChunk → chunk metadata with overlapping keywords
                return _FakeAllResult([
                    ('text', {'keywords': ['safety', 'procedure', 'installation']}),
                    ('text', {'keywords': ['torque', 'bolt', 'specification']}),
                ])
            if self._call == 3:
                # select DocumentSection titles
                return _FakeResult([])
            if self._call == 4:
                # select GraphNode (peer doc nodes)
                return _FakeResult([peer_node])
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

    # Check edges: should have 'related' edges with meaningful weight (not blind 'similar')
    from shared.models.database.document import GraphEdge
    edges = [obj for obj in db.added if isinstance(obj, GraphEdge)]
    # Whether an edge is created depends on the keyword overlap score
    # The peer has 5 keywords, doc has 6 keywords, they share ≥3
    for edge in edges:
        assert edge.edge_kind == 'related'
        assert edge.weight > 0
        assert 'shared_keywords' in (edge.properties or {})


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

    class _FakeRedisService:
        def incr(self, key: str) -> int:
            incremented_keys.append(f'knowhere-api:{key}')
            return len(incremented_keys)

    monkeypatch.setattr(
        lifecycle_module,
        'SyncRedisServiceFactory',
        type('F', (), {'get_service': staticmethod(lambda: _FakeRedisService())}),
    )

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
    assert all(key.startswith('knowhere-api:retrieval:version:') for key in incremented_keys)


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
