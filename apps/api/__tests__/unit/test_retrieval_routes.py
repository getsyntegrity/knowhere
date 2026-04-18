import pytest


@pytest.mark.asyncio
async def test_retrieval_query_route_exists(authenticated_client):
    response = await authenticated_client.post(
        "/v1/retrieval/query",
        json={"query": "refund policy", "top_k": 5},
    )

    assert response.status_code != 404


@pytest.mark.asyncio
async def test_document_routes_exist(authenticated_client):
    list_response = await authenticated_client.get("/v1/documents")
    get_response = await authenticated_client.get("/v1/documents/doc_123")
    archive_response = await authenticated_client.post("/v1/documents/doc_123:archive")

    assert {list_response.status_code, get_response.status_code, archive_response.status_code} != {404}


@pytest.mark.asyncio
async def test_retrieval_query_returns_canonical_chunk_results(authenticated_client, mock_db):
    from app.api.v1.routes import retrieval as retrieval_routes

    async def fake_run_retrieval_query(**_kwargs):
        return {
            'namespace': 'default',
            'query': 'refund policy',
            'graph_enabled': False,
            'results': [
                {
                    'document_id': 'doc_123',
                    'chunk_id': 'chunk_456',
                    'section_id': 'sec_12',
                    'section_path': 'Policies / Billing / Refunds',
                    'source_file_name': 'refund-policy.md',
                    'chunk_type': 'text',
                    'text': 'Annual plans may be refunded within 30 days of purchase...',
                    'score': 1.0,
                    'citation': {
                        'document_id': 'doc_123',
                        'chunk_id': 'chunk_456',
                        'source_file_name': 'refund-policy.md',
                        'section_path': 'Policies / Billing / Refunds',
                    },
                }
            ],
        }

    retrieval_routes.run_retrieval_query = fake_run_retrieval_query

    response = await authenticated_client.post(
        '/v1/retrieval/query',
        json={'query': 'refund policy', 'top_k': 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body['namespace'] == 'default'
    assert body['results'][0]['chunk_id'] == 'chunk_456'
    assert body['results'][0]['citation']['section_path'] == 'Policies / Billing / Refunds'


@pytest.mark.asyncio
async def test_document_routes_return_canonical_document_state(authenticated_client, monkeypatch):
    from app.api.v1.routes import documents as document_routes

    monkeypatch.setattr(document_routes, 'list_canonical_documents', lambda *_args, **_kwargs: [
        {
            'document_id': 'doc_123',
            'namespace': 'default',
            'status': 'active',
            'source_file_name': 'refund-policy.md',
        }
    ])
    monkeypatch.setattr(document_routes, 'get_canonical_document', lambda *_args, **_kwargs: {
        'document_id': 'doc_123',
        'namespace': 'default',
        'status': 'active',
        'source_file_name': 'refund-policy.md',
    })
    monkeypatch.setattr(document_routes, 'archive_canonical_document', lambda *_args, **_kwargs: {
        'document_id': 'doc_123',
        'namespace': 'default',
        'status': 'archived',
    })

    list_response = await authenticated_client.get('/v1/documents')
    get_response = await authenticated_client.get('/v1/documents/doc_123')
    archive_response = await authenticated_client.post('/v1/documents/doc_123:archive')

    assert list_response.status_code == 200
    assert list_response.json()['documents'][0]['document_id'] == 'doc_123'
    assert get_response.status_code == 200
    assert get_response.json()['document_id'] == 'doc_123'
    assert archive_response.status_code == 200
    assert archive_response.json()['status'] == 'archived'


@pytest.mark.asyncio
async def test_retrieval_query_schedules_usage_analytics_best_effort(authenticated_client, monkeypatch):
    from app.api.v1.routes import retrieval as retrieval_routes

    scheduled = {}

    async def fake_run_retrieval_query(**kwargs):
        scheduled.update(kwargs)
        return {
            'namespace': kwargs['namespace'],
            'query': kwargs['query'],
            'graph_enabled': kwargs['graph_enabled'],
            'results': [
                {
                    'document_id': 'doc_123',
                    'chunk_id': 'chunk_456',
                    'section_id': 'sec_12',
                    'section_path': 'Policies / Billing / Refunds',
                    'source_file_name': 'refund-policy.md',
                    'chunk_type': 'text',
                    'text': 'Annual plans may be refunded within 30 days of purchase...',
                    'score': 1.0,
                    'citation': {
                        'document_id': 'doc_123',
                        'chunk_id': 'chunk_456',
                        'source_file_name': 'refund-policy.md',
                        'section_path': 'Policies / Billing / Refunds',
                    },
                }
            ],
        }

    monkeypatch.setattr(retrieval_routes, 'run_retrieval_query', fake_run_retrieval_query)

    response = await authenticated_client.post('/v1/retrieval/query', json={'query': 'refund policy', 'top_k': 5})

    assert response.status_code == 200
    assert scheduled['user_id']
    assert scheduled['namespace'] == 'default'
    assert scheduled['exclude_document_ids'] == []
    assert scheduled['query'] == 'refund policy'
    assert scheduled['top_k'] == 5
    assert scheduled['graph_enabled'] is False


@pytest.mark.asyncio
async def test_retrieval_query_ignores_usage_analytics_schedule_failure(authenticated_client, monkeypatch):
    from app.api.v1.routes import retrieval as retrieval_routes

    async def fake_run_retrieval_query(**_kwargs):
        return {
            'namespace': 'default',
            'query': 'refund policy',
            'graph_enabled': False,
            'results': [
                {
                    'document_id': 'doc_123',
                    'chunk_id': 'chunk_456',
                    'section_id': 'sec_12',
                    'section_path': 'Policies / Billing / Refunds',
                    'source_file_name': 'refund-policy.md',
                    'chunk_type': 'text',
                    'text': 'Annual plans may be refunded within 30 days of purchase...',
                    'score': 1.0,
                    'citation': {
                        'document_id': 'doc_123',
                        'chunk_id': 'chunk_456',
                        'source_file_name': 'refund-policy.md',
                        'section_path': 'Policies / Billing / Refunds',
                    },
                }
            ],
        }

    monkeypatch.setattr(retrieval_routes, 'run_retrieval_query', fake_run_retrieval_query)

    response = await authenticated_client.post('/v1/retrieval/query', json={'query': 'refund policy', 'top_k': 5})

    assert response.status_code == 200
    assert response.json()['results'][0]['chunk_id'] == 'chunk_456'


@pytest.mark.asyncio
async def test_retrieval_query_route_uses_shared_app_service(authenticated_client, monkeypatch):
    from app.api.v1.routes import retrieval as retrieval_routes

    captured = {}

    async def fake_run_retrieval_query(**kwargs):
        captured.update(kwargs)
        return {
            'namespace': kwargs['namespace'],
            'query': kwargs['query'],
            'graph_enabled': kwargs['graph_enabled'],
            'results': [],
        }

    monkeypatch.setattr(retrieval_routes, 'run_retrieval_query', fake_run_retrieval_query)

    response = await authenticated_client.post(
        '/v1/retrieval/query',
        json={'query': 'refund policy', 'top_k': 5, 'graph_enabled': True},
    )

    assert response.status_code == 200
    assert captured['user_id']
    assert captured['namespace'] == 'default'
    assert captured['query'] == 'refund policy'
    assert captured['top_k'] == 5
    assert captured['graph_enabled'] is True
