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

    retrieval_routes.list_canonical_chunks = lambda *_args, **_kwargs: [
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
async def test_document_routes_return_canonical_document_state(authenticated_client):
    from app.api.v1.routes import documents as document_routes

    document_routes.list_canonical_documents = lambda *_args, **_kwargs: [
        {
            'document_id': 'doc_123',
            'namespace': 'default',
            'status': 'active',
            'source_file_name': 'refund-policy.md',
        }
    ]
    document_routes.get_canonical_document = lambda *_args, **_kwargs: {
        'document_id': 'doc_123',
        'namespace': 'default',
        'status': 'active',
        'source_file_name': 'refund-policy.md',
    }
    document_routes.archive_canonical_document = lambda *_args, **_kwargs: {
        'document_id': 'doc_123',
        'namespace': 'default',
        'status': 'archived',
    }

    list_response = await authenticated_client.get('/v1/documents')
    get_response = await authenticated_client.get('/v1/documents/doc_123')
    archive_response = await authenticated_client.post('/v1/documents/doc_123:archive')

    assert list_response.status_code == 200
    assert list_response.json()['documents'][0]['document_id'] == 'doc_123'
    assert get_response.status_code == 200
    assert get_response.json()['document_id'] == 'doc_123'
    assert archive_response.status_code == 200
    assert archive_response.json()['status'] == 'archived'
