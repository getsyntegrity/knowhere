from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_retrieval_query_route_exists(authenticated_client):
    response = await authenticated_client.post(
        "/v1/retrieval/query",
        json={"query": "refund policy", "top_k": 5},
    )

    assert response.status_code != 404


@pytest.mark.asyncio
async def test_document_routes_exist(authenticated_client, monkeypatch):
    from app.api.v1.routes import documents as document_routes

    class FakeDocumentService:
        async def list_documents(self, *_args, **_kwargs):
            return []

        async def get_document(self, *_args, **_kwargs):
            return None

        async def archive_document(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(document_routes, 'DocumentService', FakeDocumentService)

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
                    'content': 'Annual plans may be refunded within 30 days of purchase...',
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
    assert body['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'
    assert body['results'][0]['citation']['section_path'] == 'Policies / Billing / Refunds'


@pytest.mark.asyncio
async def test_document_routes_return_canonical_document_state(authenticated_client, monkeypatch):
    from app.api.v1.routes import documents as document_routes

    class FakeDocumentService:
        async def list_documents(self, *_args, **_kwargs):
            return [
                {
                    'document_id': 'doc_123',
                    'namespace': 'default',
                    'status': 'active',
                    'source_file_name': 'refund-policy.md',
                }
            ]

        async def get_document(self, *_args, **_kwargs):
            return {
                'document_id': 'doc_123',
                'namespace': 'default',
                'status': 'active',
                'source_file_name': 'refund-policy.md',
            }

        async def archive_document(self, *_args, **_kwargs):
            return {
                'document_id': 'doc_123',
                'namespace': 'default',
                'status': 'archived',
            }

    monkeypatch.setattr(document_routes, 'DocumentService', FakeDocumentService)

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
                    'content': 'Annual plans may be refunded within 30 days of purchase...',
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
    assert scheduled['exclude_sections'] == []
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
                    'content': 'Annual plans may be refunded within 30 days of purchase...',
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


@pytest.mark.asyncio
async def test_retrieval_query_route_returns_cached_result_from_shared_service(authenticated_client, monkeypatch):
    from app.api.v1.routes import retrieval as retrieval_routes

    async def fake_run_retrieval_query(**_kwargs):
        return {
            'namespace': 'default',
            'query': 'refund policy',
            'graph_enabled': False,
            'results': [
                {
                    'document_id': 'doc_cached',
                    'chunk_id': 'chunk_cached',
                    'section_id': 'sec_12',
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

    monkeypatch.setattr(retrieval_routes, 'run_retrieval_query', fake_run_retrieval_query)

    response = await authenticated_client.post('/v1/retrieval/query', json={'query': 'refund policy', 'top_k': 5})

    assert response.status_code == 200
    assert response.json()['results'][0]['chunk_id'] == 'chunk_cached'


@pytest.mark.asyncio
async def test_retrieval_query_route_passes_section_exclusions(authenticated_client, monkeypatch):
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
        json={
            'query': 'refund policy',
            'top_k': 5,
            'exclude_sections': [{'document_id': 'doc_123', 'section_path': 'Policies / Billing'}],
        },
    )

    assert response.status_code == 200
    assert captured['exclude_sections'] == [{'document_id': 'doc_123', 'section_path': 'Policies / Billing'}]


@pytest.mark.asyncio
async def test_retrieval_asset_url_helper_works_in_api_runtime(monkeypatch):
    from shared.services.retrieval.app_service import generate_retrieval_asset_url

    captured = {}

    class FakeResultStorage:
        def generate_artifact_url(self, *, job_id, artifact_ref, expires_in=3600):
            captured.update({'job_id': job_id, 'artifact_ref': artifact_ref, 'expires_in': expires_in})
            return 'https://assets.test/results/job_123/images/page-1.png?signature=fresh'

        def normalize_artifact_ref(self, artifact_ref):
            return artifact_ref

    monkeypatch.setattr('shared.services.retrieval.app_service.get_result_storage', lambda: FakeResultStorage())

    assert await generate_retrieval_asset_url(job_id='job_123', artifact_ref='images/page-1.png') == (
        'https://assets.test/results/job_123/images/page-1.png?signature=fresh'
    )
    assert captured == {'job_id': 'job_123', 'artifact_ref': 'images/page-1.png', 'expires_in': 3600}


@pytest.mark.asyncio
async def test_archive_canonical_document_invalidates_namespace_cache_best_effort(monkeypatch):
    from app.services.document_service import DocumentService
    from shared.models.database.document import Document

    document = Document(
        document_id='doc_123',
        user_id='user_123',
        namespace='default',
        status='active',
        current_job_result_id='result_123',
        source_file_name='refund-policy.md',
    )

    class FakeResult:
        def scalar_one_or_none(self):
            return document

    class FakeDb:
        def __init__(self):
            self.commit_called = False
            self.run_sync_called = False

        async def execute(self, _stmt):
            return FakeResult()

        async def run_sync(self, fn):
            self.run_sync_called = True
            fn(object())

        async def commit(self):
            self.commit_called = True
            document.status = 'archived'
            from datetime import datetime
            document.archived_at = datetime.utcnow()

    invalidation = {}

    class FakeGraphService:
        def remove_document_graph(self, _db, *, scope, document_id):
            invalidation['graph_scope_namespace'] = scope.namespace
            invalidation['graph_document_id'] = document_id

    async def fake_invalidate_retrieval_cache_namespaces(*, user_id, namespaces):
        invalidation['user_id'] = user_id
        invalidation['namespaces'] = namespaces

    monkeypatch.setattr('app.services.document_service.DocumentGraphService', FakeGraphService)
    monkeypatch.setattr('app.services.document_service.invalidate_retrieval_cache_namespaces', fake_invalidate_retrieval_cache_namespaces)

    result = await DocumentService().archive_document(
        FakeDb(),
        user_id='user_123',
        document_id='doc_123',
    )

    assert result['status'] == 'archived'
    assert invalidation['user_id'] == 'user_123'
    assert invalidation['namespaces'] == ['default']
    assert invalidation['graph_scope_namespace'] == 'default'
    assert invalidation['graph_document_id'] == 'doc_123'


def test_document_routes_keep_db_logic_out_of_router():
    source = (
        Path(__file__).parents[2]
        / 'app/api/v1/routes/documents.py'
    ).read_text(encoding='utf-8')

    assert 'inspect.isawaitable' not in source
    assert 'select(Document)' not in source
