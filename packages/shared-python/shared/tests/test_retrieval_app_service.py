import pytest


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
                "text": "Annual plans may be refunded within 30 days of purchase...",
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
        graph_enabled=True,
    )

    assert [name for name, _ in calls] == ['graph', 'lexical']
    assert result['namespace'] == 'default'
    assert result['query'] == 'refund policy'
    assert result['graph_enabled'] is False
    assert result['results'][0]['chunk_id'] == 'chunk_456'
    assert result['results'][0]['citation']['section_path'] == 'Policies / Billing / Refunds'
    assert scheduled['user_id'] == 'user_123'
    assert scheduled['namespace'] == 'default'


@pytest.mark.asyncio
async def test_run_retrieval_query_serves_cached_result_without_hitting_db_path(monkeypatch):
    from shared.services.retrieval import app_service

    lexical_calls = []

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return {
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
                    'text': 'cached result',
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
                'text': 'Annual plans may be refunded within 30 days of purchase...',
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
        graph_enabled=False,
    )

    assert lexical_calls == ['lexical']
    assert result['results'][0]['chunk_id'] == 'chunk_456'


@pytest.mark.asyncio
async def test_run_retrieval_query_writes_cache_after_db_result(monkeypatch):
    from shared.services.retrieval import app_service

    cached_write = {}

    async def fake_get_cached_retrieval_query_result(**_kwargs):
        return None

    async def fake_list_canonical_chunks(*_args, **_kwargs):
        return [
            {
                'document_id': 'doc_123',
                'chunk_id': 'chunk_456',
                'section_id': 'sec_12',
                'section_path': 'Policies / Billing / Refunds',
                'source_file_name': 'refund-policy.md',
                'chunk_type': 'text',
                'text': 'Annual plans may be refunded within 30 days of purchase...',
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
        graph_enabled=False,
    )

    assert result['results'][0]['chunk_id'] == 'chunk_456'
    assert cached_write['user_id'] == 'user_123'
    assert cached_write['namespace'] == 'default'
    assert cached_write['query'] == 'refund policy'
    assert cached_write['top_k'] == 5
    assert cached_write['exclude_document_ids'] == ['doc_skip']
    assert cached_write['graph_enabled'] is False
    assert cached_write['response']['results'][0]['chunk_id'] == 'chunk_456'
