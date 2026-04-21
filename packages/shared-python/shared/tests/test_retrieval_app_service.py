import asyncio
import os

import pytest
from types import SimpleNamespace
from pathlib import Path

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


async def _empty_lexical_chunks(*_args, **_kwargs):
    return [], []


@pytest.mark.asyncio
async def test_list_lexical_chunks_does_not_overlap_db_execute_calls(monkeypatch):
    from shared.services.retrieval import app_service

    class FakeResult:
        def all(self) -> list[tuple[object, object, object, object]]:
            return []

    class FakeDB:
        def __init__(self) -> None:
            self.active_calls = 0
            self.max_active_calls = 0

        async def execute(self, _stmt) -> FakeResult:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
            await asyncio.sleep(0)
            self.active_calls -= 1
            return FakeResult()

    db = FakeDB()

    await app_service.list_lexical_chunks(
        db,
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert db.max_active_calls == 1


@pytest.mark.asyncio
async def test_run_retrieval_query_does_not_overlap_lexical_and_graph_db_work(monkeypatch):
    from shared.services.retrieval import app_service

    tracker = {
        'active_calls': 0,
        'max_active_calls': 0,
    }

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 1, None

    async def fake_set_cached_retrieval_query_result(**_kwargs):
        return None

    async def fake_list_lexical_chunks(*_args, **_kwargs):
        tracker['active_calls'] += 1
        tracker['max_active_calls'] = max(tracker['max_active_calls'], tracker['active_calls'])
        await asyncio.sleep(0)
        tracker['active_calls'] -= 1
        return [], []

    async def fake_list_graph_routed_chunks(*_args, **_kwargs):
        tracker['active_calls'] += 1
        tracker['max_active_calls'] = max(tracker['max_active_calls'], tracker['active_calls'])
        await asyncio.sleep(0)
        tracker['active_calls'] -= 1
        return []

    async def fake_assemble_retrieval_results(*_args, **_kwargs):
        return []

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', fake_list_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'assemble_retrieval_results', fake_assemble_retrieval_results)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert result['results'] == []
    assert tracker['max_active_calls'] == 1


@pytest.mark.asyncio
async def test_run_retrieval_query_always_uses_graph_routing(monkeypatch):
    from shared.services.retrieval import app_service

    calls = []

    async def fake_graph(*_args, **kwargs):
        calls.append(('graph', kwargs))
        return [
            {
                "document_id": "doc_123",
                "chunk_id": "chunk_456",
                "section_id": "sec_12",
                "section_path": "Policies / Billing / Refunds",
                "source_file_name": "refund-policy.md",
                "chunk_type": "text",
                "content": "Annual plans may be refunded within 30 days of purchase...",
                "score": 1.0,
                "file_path": None,
            }
        ]

    scheduled = {}

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', lambda **_kwargs: None)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', lambda **_kwargs: None)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_graph)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **kwargs: scheduled.update(kwargs))

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert [name for name, _ in calls] == ['graph']
    assert result['namespace'] == 'default'
    assert result['query'] == 'refund policy'
    assert result['results'][0]['chunk_id'] == 'chunk_456'
    assert result['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'
    assert result['results'][0]['citation']['section_path'] == 'Policies / Billing / Refunds'
    assert scheduled['user_id'] == 'user_123'
    assert scheduled['namespace'] == 'default'


@pytest.mark.asyncio
async def test_run_retrieval_query_serves_cached_result_without_hitting_db_path(monkeypatch):
    from shared.services.retrieval import app_service

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 4, {
            'namespace': 'default',
            'query': 'refund policy',
            'results': [
                {
                    'document_id': 'doc_cached',
                    'chunk_id': 'chunk_cached',
                    'section_id': 'sec_cached',
                    'section_path': 'Policies / Billing / Refunds',
                    'source_file_name': 'refund-policy.md',
                    'chunk_type': 'text',
                    'content': 'cached result',
                    'score': 1.0,
                    'citation': {
                        'document_id': 'doc_cached',
                        'chunk_id': 'chunk_cached',
                        'source_file_name': 'refund-policy.md',
                        'section_path': 'Policies / Billing / Refunds',
                    },
                }
            ],
        }

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    scheduled = {}
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **kwargs: scheduled.update(kwargs))

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert result['results'][0]['chunk_id'] == 'chunk_cached'
    assert scheduled['user_id'] == 'user_123'
    assert scheduled['namespace'] == 'default'


@pytest.mark.asyncio
async def test_run_retrieval_query_falls_back_to_db_when_cache_read_fails(monkeypatch):
    from shared.services.retrieval import app_service

    graph_calls = []

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        raise RuntimeError('redis down')

    async def fake_list_graph_routed_chunks(*_args, **_kwargs):
        graph_calls.append('graph')
        return [
            {
                'document_id': 'doc_123',
                'chunk_id': 'chunk_456',
                'section_id': 'sec_12',
                'section_path': 'Policies / Billing / Refunds',
                'source_file_name': 'refund-policy.md',
                'chunk_type': 'text',
                'content': 'Annual plans may be refunded within 30 days of purchase...',
                'score': 1.0,
                'file_path': None,
            }
        ]

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert graph_calls == ['graph']
    assert result['results'][0]['chunk_id'] == 'chunk_456'


@pytest.mark.asyncio
async def test_run_retrieval_query_writes_cache_after_db_result(monkeypatch):
    from shared.services.retrieval import app_service

    cached_write = {}

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 3, None

    async def fake_list_graph_routed_chunks(*_args, **_kwargs):
        return [
            {
                'document_id': 'doc_123',
                'chunk_id': 'chunk_456',
                'section_id': 'sec_12',
                'section_path': 'Policies / Billing / Refunds',
                'source_file_name': 'refund-policy.md',
                'chunk_type': 'text',
                'content': 'Annual plans may be refunded within 30 days of purchase...',
                'score': 1.0,
                'file_path': None,
            }
        ]

    async def fake_set_cached_retrieval_query_result(**kwargs):
        cached_write.update(kwargs)

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=['doc_skip'],
        exclude_sections=[],
    )

    assert result['results'][0]['chunk_id'] == 'chunk_456'
    assert cached_write['version'] == 3
    assert cached_write['user_id'] == 'user_123'
    assert cached_write['namespace'] == 'default'
    assert cached_write['query'] == 'refund policy'
    assert cached_write['top_k'] == 5
    assert cached_write['exclude_document_ids'] == ['doc_skip']
    assert cached_write['exclude_sections'] == []
    assert cached_write['response']['results'][0]['chunk_id'] == 'chunk_456'


@pytest.mark.asyncio
async def test_run_retrieval_query_returns_asset_url_without_caching_signed_url(monkeypatch):
    from shared.services.retrieval import app_service

    cached_write = {}
    generated = []

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 3, None

    async def fake_list_graph_routed_chunks(*_args, **_kwargs):
        return [
            {
                'document_id': 'doc_123',
                'chunk_id': 'chunk_image',
                'section_id': 'sec_12',
                'section_path': 'Drawings / Images',
                'source_file_name': 'drawing.pdf',
                'chunk_type': 'image',
                'content': 'OCR caption',
                'score': 1.0,
                'file_path': 'images/page-1.png',
                'job_id': 'job_123',
            }
        ]

    class FakeResultStorage:
        def normalize_artifact_ref(self, artifact_ref):
            return artifact_ref

        def generate_artifact_url(self, *, job_id, artifact_ref, expires_in=3600):
            generated.append((job_id, artifact_ref, expires_in))
            return f'https://assets.test/{job_id}/{artifact_ref}?signature=fresh'

    async def fake_set_cached_retrieval_query_result(**kwargs):
        cached_write.update(kwargs)

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'get_result_storage', lambda: FakeResultStorage())
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    public_result = result['results'][0]
    assert public_result['asset_url'] == 'https://assets.test/job_123/images/page-1.png?signature=fresh'
    assert generated == [('job_123', 'images/page-1.png', 3600)]
    assert 'file_path' not in public_result
    assert 'file_path' not in public_result['citation']
    cached_result = cached_write['response']['results'][0]
    assert cached_result['file_path'] == 'images/page-1.png'
    assert 'asset_url' not in cached_result
    assert 'asset_url' not in cached_result['citation']


@pytest.mark.asyncio
async def test_run_retrieval_query_adds_fresh_asset_url_to_cached_media_result(monkeypatch):
    from shared.services.retrieval import app_service

    generated = []

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 4, {
            'namespace': 'default',
            'query': 'drawing',
            'results': [
                {
                    'document_id': 'doc_cached',
                    'chunk_id': 'chunk_cached',
                    'section_id': 'sec_cached',
                    'section_path': 'Drawings / Images',
                    'source_file_name': 'drawing.pdf',
                    'chunk_type': 'image',
                    'content': 'cached caption',
                    'score': 1.0,
                    'file_path': 'images/page-1.png',
                    'job_id': 'job_123',
                    'citation': {
                        'document_id': 'doc_cached',
                        'chunk_id': 'chunk_cached',
                        'source_file_name': 'drawing.pdf',
                        'section_path': 'Drawings / Images',
                    },
                }
            ],
        }

    class FakeResultStorage:
        def normalize_artifact_ref(self, artifact_ref):
            return artifact_ref

        def generate_artifact_url(self, *, job_id, artifact_ref, expires_in=3600):
            generated.append((job_id, artifact_ref, expires_in))
            return f'https://assets.test/{job_id}/{artifact_ref}?signature=fresh'

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'get_result_storage', lambda: FakeResultStorage())
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert generated == [('job_123', 'images/page-1.png', 3600)]
    public_result = result['results'][0]
    assert public_result['asset_url'] == 'https://assets.test/job_123/images/page-1.png?signature=fresh'
    assert 'file_path' not in public_result


@pytest.mark.asyncio
async def test_run_retrieval_query_real_helper_generates_asset_url_in_api_runtime(monkeypatch):
    from shared.services.retrieval import app_service

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 4, {
            'namespace': 'default',
            'query': 'drawing',
            'results': [
                {
                    'document_id': 'doc_cached',
                    'chunk_id': 'chunk_cached',
                    'section_id': 'sec_cached',
                    'section_path': 'Drawings / Images',
                    'source_file_name': 'drawing.pdf',
                    'chunk_type': 'image',
                    'content': 'cached caption',
                    'score': 1.0,
                    'file_path': 'images/page-1.png',
                    'job_id': 'job_123',
                    'citation': {
                        'document_id': 'doc_cached',
                        'chunk_id': 'chunk_cached',
                        'source_file_name': 'drawing.pdf',
                        'section_path': 'Drawings / Images',
                    },
                }
            ],
        }

    class FakeResultStorage:
        def normalize_artifact_ref(self, artifact_ref):
            return artifact_ref

        def generate_artifact_url(self, *, job_id, artifact_ref, expires_in=3600):
            assert job_id == 'job_123'
            assert artifact_ref == 'images/page-1.png'
            assert expires_in == 3600
            return 'https://assets.test/results/job_123/images/page-1.png?signature=fresh'

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'get_result_storage', lambda: FakeResultStorage())
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    public_result = result['results'][0]
    assert public_result['asset_url'] == 'https://assets.test/results/job_123/images/page-1.png?signature=fresh'
    assert 'file_path' not in public_result
    assert 'file_path' not in public_result['citation']


@pytest.mark.asyncio
async def test_run_retrieval_query_does_not_expose_raw_file_path_when_asset_url_is_unavailable(monkeypatch):
    from shared.services.retrieval import app_service

    generated = []

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 4, {
            'namespace': 'default',
            'query': 'drawing',
            'results': [
                {
                    'document_id': 'doc_cached',
                    'chunk_id': 'chunk_cached',
                    'section_id': 'sec_cached',
                    'section_path': 'Drawings / Images',
                    'source_file_name': 'drawing.pdf',
                    'chunk_type': 'image',
                    'content': 'cached caption',
                    'score': 1.0,
                    'file_path': 'images/page-1.png',
                    'citation': {
                        'document_id': 'doc_cached',
                        'chunk_id': 'chunk_cached',
                        'source_file_name': 'drawing.pdf',
                        'section_path': 'Drawings / Images',
                        'file_path': 'images/page-1.png',
                    },
                }
            ],
        }

    class FakeResultStorage:
        def normalize_artifact_ref(self, artifact_ref):
            return artifact_ref

        def generate_artifact_url(self, *, job_id, artifact_ref, expires_in=3600):
            generated.append((job_id, artifact_ref, expires_in))
            return f'https://assets.test/{job_id}/{artifact_ref}?signature=fresh'

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'get_result_storage', lambda: FakeResultStorage())
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert generated == []
    public_result = result['results'][0]
    assert 'asset_url' not in public_result
    assert 'file_path' not in public_result
    assert 'file_path' not in public_result['citation']


@pytest.mark.asyncio
async def test_run_retrieval_query_does_not_generate_asset_url_for_text_chunk(monkeypatch):
    from shared.services.retrieval import app_service

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 3, None

    async def fake_list_graph_routed_chunks(*_args, **_kwargs):
        return [
            {
                'document_id': 'doc_123',
                'chunk_id': 'chunk_text',
                'section_id': 'sec_12',
                'section_path': 'Policies / Billing',
                'source_file_name': 'refund-policy.md',
                'chunk_type': 'text',
                'content': 'Annual plans may be refunded within 30 days.',
                'score': 1.0,
                'file_path': 'results/job_123/images/ignored.png',
            }
        ]

    class FailResultStorage:
        def normalize_artifact_ref(self, artifact_ref):
            raise AssertionError('text chunks should not inspect result artifacts')

        def generate_artifact_url(self, *, job_id, artifact_ref, expires_in=3600):
            raise AssertionError('text chunks should not receive asset URLs')

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', lambda **_kwargs: None)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'get_result_storage', lambda: FailResultStorage())
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    public_result = result['results'][0]
    assert 'asset_url' not in public_result
    assert 'file_path' not in public_result
    assert 'file_path' not in public_result['citation']


def test_document_chunk_schema_has_lexical_serving_fields():
    source = (Path(__file__).parents[1] / "models/database/document.py").read_text(
        encoding="utf-8"
    )

    assert "path_lexical_text" in source
    assert "content_lexical_text" in source


def test_retrieval_query_uses_lexical_serving_fields():
    shared_root = Path(__file__).parents[1]
    graph_source = (shared_root / "services/retrieval/graph_service.py").read_text(
        encoding="utf-8"
    )

    assert "DocumentChunk.content.ilike" not in graph_source
    assert "content_lexical_text" in graph_source
    assert "path_lexical_text" in graph_source


@pytest.mark.asyncio
async def test_run_retrieval_query_passes_section_exclusions_to_cache_and_db_paths(monkeypatch):
    from shared.services.retrieval import app_service

    captured = {}

    async def fake_get_cached_retrieval_query_result(**kwargs):
        captured['cache_read'] = kwargs
        return 5, None

    async def fake_list_graph_routed_chunks(*_args, **kwargs):
        captured['graph'] = kwargs
        return []

    async def fake_set_cached_retrieval_query_result(**kwargs):
        captured['cache_write'] = kwargs

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    exclude_sections = [{'document_id': 'doc_123', 'section_path': 'Policies / Billing'}]
    await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=['doc_skip'],
        exclude_sections=exclude_sections,
    )

    assert captured['cache_read']['exclude_sections'] == exclude_sections
    assert captured['graph']['exclude_sections'] == exclude_sections
    assert captured['cache_write']['exclude_sections'] == exclude_sections


@pytest.mark.asyncio
async def test_assemble_result_content_inlines_connected_tables_after_exclusions():
    from shared.services.retrieval import app_service

    rows = [
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_text',
            'section_id': 'sec_text',
            'section_path': 'Policies / Billing',
            'source_file_name': 'refund-policy.md',
            'chunk_type': 'text',
            'content': 'Base refund policy text',
            'score': 1.0,
            'file_path': None,
            'chunk_metadata': {
                'connect_to': [
                    {'target': 'chunk_table_keep', 'relation': 'embeds'},
                    {'target': 'chunk_table_excluded', 'relation': 'embeds'},
                ]
            },
        },
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_table_keep',
            'section_id': 'sec_table_keep',
            'section_path': 'Policies / Billing / Refund Table',
            'source_file_name': 'refund-policy.md',
            'chunk_type': 'table',
            'content': 'Refund table content',
            'score': 1.0,
            'file_path': 'tables/refunds.html',
            'chunk_metadata': {},
        },
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_table_excluded',
            'section_id': 'sec_table_excluded',
            'section_path': 'Policies / Internal Only',
            'source_file_name': 'refund-policy.md',
            'chunk_type': 'table',
            'content': 'Excluded table content',
            'score': 1.0,
            'file_path': 'tables/internal.html',
            'chunk_metadata': {},
        },
    ]

    assembled = await app_service.assemble_retrieval_results(
        rows=rows,
        exclude_document_ids=[],
        exclude_sections=[{'document_id': 'doc_123', 'section_path': 'Policies / Internal Only'}],
    )

    assert len(assembled) == 1
    assert assembled[0]['chunk_id'] == 'chunk_text'
    assert assembled[0]['content'] == 'Base refund policy text\n\nRefund table content'


@pytest.mark.asyncio
async def test_assemble_result_content_hydrates_missing_connected_table_from_canonical_state(monkeypatch):
    from shared.services.retrieval import app_service

    async def fake_hydrate(*, db, rows, exclude_document_ids, exclude_sections):
        return [
            {
                'document_id': 'doc_123',
                'chunk_id': 'chunk_table_keep',
                'section_id': 'sec_table_keep',
                'section_path': 'Policies / Billing / Refund Table',
                'source_file_name': 'refund-policy.md',
                'chunk_type': 'table',
                'content': 'Refund table content',
                'score': 1.0,
                'file_path': 'tables/refunds.html',
                'chunk_metadata': {},
                'job_result_id': 'result_123',
            }
        ]

    monkeypatch.setattr(app_service, 'hydrate_connected_target_rows', fake_hydrate)

    rows = [
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_text',
            'section_id': 'sec_text',
            'section_path': 'Policies / Billing',
            'source_file_name': 'refund-policy.md',
            'chunk_type': 'text',
            'content': 'Base refund policy text',
            'score': 1.0,
            'file_path': None,
            'chunk_metadata': {
                'connect_to': [
                    {'target': 'chunk_table_keep', 'relation': 'embeds'},
                ]
            },
            'job_result_id': 'result_123',
        },
    ]

    assembled = await app_service.assemble_retrieval_results(
        db=object(),
        rows=rows,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert len(assembled) == 1
    assert assembled[0]['content'] == 'Base refund policy text\n\nRefund table content'


@pytest.mark.asyncio
async def test_assemble_result_content_keeps_table_chunk_content_as_self():
    from shared.services.retrieval import app_service

    rows = [
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_table',
            'section_id': 'sec_table',
            'section_path': 'Policies / Billing / Refund Table',
            'source_file_name': 'refund-policy.md',
            'chunk_type': 'table',
            'content': 'Refund table content',
            'score': 1.0,
            'file_path': 'tables/refunds.html',
            'chunk_metadata': {
                'connect_to': [{'target': 'chunk_text', 'relation': 'embeds'}],
            },
        },
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_text',
            'section_id': 'sec_text',
            'section_path': 'Policies / Billing',
            'source_file_name': 'refund-policy.md',
            'chunk_type': 'text',
            'content': 'Base refund policy text',
            'score': 1.0,
            'file_path': None,
            'chunk_metadata': {},
        },
    ]

    assembled = await app_service.assemble_retrieval_results(
        rows=rows,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert len(assembled) == 1
    assert assembled[0]['chunk_id'] == 'chunk_table'
    assert assembled[0]['content'] == 'Refund table content'


@pytest.mark.asyncio
async def test_run_retrieval_query_uses_pinned_cache_version_for_write(monkeypatch):
    from shared.services.retrieval import app_service

    cached_write = {}

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 9, None

    async def fake_list_graph_routed_chunks(*_args, **_kwargs):
        return []

    async def fake_set_cached_retrieval_query_result(**kwargs):
        cached_write.update(kwargs)

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_lexical_chunks', _empty_lexical_chunks)
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_list_graph_routed_chunks)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert cached_write['version'] == 9


@pytest.mark.asyncio
async def test_list_graph_routed_chunks_fills_top_k_after_section_exclusion():
    from shared.services.retrieval.graph_service import GraphQueryService

    def build_row(chunk_id, section_path):
        document = SimpleNamespace(
            document_id='doc_123',
            source_file_name='refund-policy.md',
        )
        chunk = SimpleNamespace(
            chunk_id=chunk_id,
            section_id=f'sec_{chunk_id}',
            chunk_type='text',
            content=f'content-{chunk_id}',
            file_path=None,
            chunk_metadata={},
            job_result_id='result_123',
            sort_order=1,
        )
        section = SimpleNamespace(section_path=section_path)
        job_result = SimpleNamespace(job_id='job_123')
        return (document, chunk, section, job_result)

    returned_rows = [
        build_row('chunk_1', 'Excluded / One'),
        build_row('chunk_2', 'Excluded / Two'),
        build_row('chunk_3', 'Excluded / Three'),
        build_row('chunk_4', 'Allowed / Four'),
        build_row('chunk_5', 'Allowed / Five'),
    ]

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            sql = str(stmt.compile(compile_kwargs={'literal_binds': True}))
            if self.calls == 1:
                assert 'LIMIT 4' in sql
                assert 'OFFSET 0' in sql or ' OFFSET ' not in sql
                return FakeResult(returned_rows[:4])
            assert 'LIMIT 4' in sql
            assert 'OFFSET 4' in sql
            return FakeResult(returned_rows[4:])

    fake_db = FakeDB()

    rows = await GraphQueryService().collect_candidate_chunks(
        fake_db,
        user_id='user_123',
        namespace='default',
        entry_document_ids=['doc_123'],
        query='refund',
        top_k=2,
        exclude_sections=[
            {'document_id': 'doc_123', 'section_path': 'Excluded / One'},
            {'document_id': 'doc_123', 'section_path': 'Excluded / Two'},
            {'document_id': 'doc_123', 'section_path': 'Excluded / Three'},
        ],
    )

    assert fake_db.calls == 2
    assert [row['chunk_id'] for row in rows] == ['chunk_4', 'chunk_5']
