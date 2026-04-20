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


@pytest.mark.asyncio
async def test_run_retrieval_query_uses_graph_then_falls_back_to_lexical(monkeypatch):
    from shared.services.retrieval import app_service

    calls = []

    async def fake_graph(*_args, **kwargs):
        calls.append(('graph', kwargs))
        return []

    async def fake_lexical(*_args, **kwargs):
        calls.append(('lexical', kwargs))
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
    monkeypatch.setattr(app_service, 'list_graph_routed_chunks', fake_graph)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_lexical)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **kwargs: scheduled.update(kwargs))

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=True,
    )

    assert [name for name, _ in calls] == ['graph', 'lexical']
    assert result['namespace'] == 'default'
    assert result['query'] == 'refund policy'
    assert result['graph_enabled'] is False
    assert result['results'][0]['chunk_id'] == 'chunk_456'
    assert result['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'
    assert result['results'][0]['citation']['section_path'] == 'Policies / Billing / Refunds'
    assert scheduled['user_id'] == 'user_123'
    assert scheduled['namespace'] == 'default'


@pytest.mark.asyncio
async def test_run_retrieval_query_serves_cached_result_without_hitting_db_path(monkeypatch):
    from shared.services.retrieval import app_service

    lexical_calls = []

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
            'graph_enabled': False,
        }

    async def fake_list_canonical_chunks(*_args, **_kwargs):
        lexical_calls.append('lexical')
        return []

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
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
        graph_enabled=False,
    )

    assert lexical_calls == []
    assert result['results'][0]['chunk_id'] == 'chunk_cached'
    assert scheduled['user_id'] == 'user_123'
    assert scheduled['namespace'] == 'default'


@pytest.mark.asyncio
async def test_run_retrieval_query_falls_back_to_db_when_cache_read_fails(monkeypatch):
    from shared.services.retrieval import app_service

    lexical_calls = []

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        raise RuntimeError('redis down')

    async def fake_list_canonical_chunks(*_args, **_kwargs):
        lexical_calls.append('lexical')
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
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
    )

    assert lexical_calls == ['lexical']
    assert result['results'][0]['chunk_id'] == 'chunk_456'


@pytest.mark.asyncio
async def test_run_retrieval_query_writes_cache_after_db_result(monkeypatch):
    from shared.services.retrieval import app_service

    cached_write = {}

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 3, None

    async def fake_list_canonical_chunks(*_args, **_kwargs):
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
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=['doc_skip'],
        exclude_sections=[],
        graph_enabled=False,
    )

    assert result['results'][0]['chunk_id'] == 'chunk_456'
    assert cached_write['version'] == 3
    assert cached_write['user_id'] == 'user_123'
    assert cached_write['namespace'] == 'default'
    assert cached_write['query'] == 'refund policy'
    assert cached_write['top_k'] == 5
    assert cached_write['exclude_document_ids'] == ['doc_skip']
    assert cached_write['exclude_sections'] == []
    assert cached_write['graph_enabled'] is False
    assert cached_write['response']['results'][0]['chunk_id'] == 'chunk_456'


@pytest.mark.asyncio
async def test_run_retrieval_query_returns_asset_url_without_caching_signed_url(monkeypatch):
    from shared.services.retrieval import app_service

    cached_write = {}

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return 3, None

    async def fake_list_canonical_chunks(*_args, **_kwargs):
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

    async def fake_generate_asset_url(*, job_id, artifact_ref):
        return f'https://assets.test/{job_id}/{artifact_ref}?signature=fresh'

    async def fake_set_cached_retrieval_query_result(**kwargs):
        cached_write.update(kwargs)

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
    monkeypatch.setattr(app_service, 'generate_retrieval_asset_url', fake_generate_asset_url)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
    )

    public_result = result['results'][0]
    assert public_result['asset_url'] == 'https://assets.test/job_123/images/page-1.png?signature=fresh'
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
            'graph_enabled': False,
        }

    async def fake_generate_asset_url(*, job_id, artifact_ref):
        generated.append((job_id, artifact_ref))
        return f'https://assets.test/{job_id}/{artifact_ref}?signature=fresh'

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', lambda *_args, **_kwargs: pytest.fail('should not hit DB path'))
    monkeypatch.setattr(app_service, 'generate_retrieval_asset_url', fake_generate_asset_url)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
    )

    assert generated == [('job_123', 'images/page-1.png')]
    public_result = result['results'][0]
    assert public_result['asset_url'] == 'https://assets.test/job_123/images/page-1.png?signature=fresh'
    assert 'file_path' not in public_result


@pytest.mark.asyncio
async def test_run_retrieval_query_real_helper_generates_asset_url_in_api_runtime(monkeypatch):
    from shared.services.retrieval import app_service
    from shared.services.storage.file_upload_service import FileUploadService

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
            'graph_enabled': False,
        }

    async def fake_generate_download_url(self, s3_key, bucket=None, expires_in=3600):
        assert s3_key == 'results/job_123/images/page-1.png'
        assert bucket is None
        assert expires_in == 3600
        return {
            'download_url': 'https://assets.test/results/job_123/images/page-1.png?signature=fresh',
            'expires_in': expires_in,
        }

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', lambda *_args, **_kwargs: pytest.fail('should not hit DB path'))
    monkeypatch.setattr(FileUploadService, 'generate_download_url', fake_generate_download_url)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
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
            'graph_enabled': False,
        }

    async def fake_generate_asset_url(*, job_id, artifact_ref):
        generated.append((job_id, artifact_ref))
        return f'https://assets.test/{job_id}/{artifact_ref}?signature=fresh'

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', lambda *_args, **_kwargs: pytest.fail('should not hit DB path'))
    monkeypatch.setattr(app_service, 'generate_retrieval_asset_url', fake_generate_asset_url)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='drawing',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
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

    async def fake_list_canonical_chunks(*_args, **_kwargs):
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

    async def fail_generate_asset_url(*, job_id, artifact_ref):
        raise AssertionError('text chunks should not receive asset URLs')

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', lambda **_kwargs: None)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
    monkeypatch.setattr(app_service, 'generate_retrieval_asset_url', fail_generate_asset_url)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    result = await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
    )

    public_result = result['results'][0]
    assert 'asset_url' not in public_result
    assert 'file_path' not in public_result
    assert 'file_path' not in public_result['citation']


@pytest.mark.asyncio
async def test_run_retrieval_query_passes_section_exclusions_to_cache_and_db_paths(monkeypatch):
    from shared.services.retrieval import app_service

    captured = {}

    async def fake_get_cached_retrieval_query_result(**kwargs):
        captured['cache_read'] = kwargs
        return 5, None

    async def fake_list_canonical_chunks(*_args, **kwargs):
        captured['lexical'] = kwargs
        return []

    async def fake_set_cached_retrieval_query_result(**kwargs):
        captured['cache_write'] = kwargs

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
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
        graph_enabled=False,
    )

    assert captured['cache_read']['exclude_sections'] == exclude_sections
    assert captured['lexical']['exclude_sections'] == exclude_sections
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

    async def fake_list_canonical_chunks(*_args, **_kwargs):
        return []

    async def fake_set_cached_retrieval_query_result(**kwargs):
        cached_write.update(kwargs)

    monkeypatch.setattr(app_service, 'get_cached_retrieval_query_result', fake_get_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'set_cached_retrieval_query_result', fake_set_cached_retrieval_query_result)
    monkeypatch.setattr(app_service, 'list_canonical_chunks', fake_list_canonical_chunks)
    monkeypatch.setattr(app_service, 'schedule_retrieval_hit_stats_update', lambda **_kwargs: None)

    await app_service.run_retrieval_query(
        db=object(),
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        graph_enabled=False,
    )

    assert cached_write['version'] == 9
