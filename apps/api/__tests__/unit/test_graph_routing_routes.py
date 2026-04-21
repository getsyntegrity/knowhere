import pytest
from unittest.mock import AsyncMock

from shared.models.database.document import Document


@pytest.mark.asyncio
async def test_retrieval_query_always_uses_graph_routing(authenticated_client, monkeypatch):
    from app.api.v1.routes import retrieval as retrieval_routes

    async def fake_run_retrieval_query(**kwargs):
        return {
            "namespace": kwargs["namespace"],
            "query": kwargs["query"],
            "results": [
                {
                    "document_id": "doc_graph",
                    "chunk_id": "chunk_graph",
                    "section_id": "sec_graph",
                    "section_path": "Policies / Billing",
                    "source_file_name": "refund-policy.md",
                    "chunk_type": "text",
                    "content": "Graph-routed refund chunk",
                    "score": 2.0,
                    "citation": {
                        "document_id": "doc_graph",
                        "chunk_id": "chunk_graph",
                        "source_file_name": "refund-policy.md",
                        "section_path": "Policies / Billing",
                    },
                }
            ],
        }

    monkeypatch.setattr(retrieval_routes, 'run_retrieval_query', fake_run_retrieval_query)

    response = await authenticated_client.post(
        "/v1/retrieval/query",
        json={"query": "refund policy", "top_k": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["chunk_id"] == "chunk_graph"


@pytest.mark.asyncio
async def test_archive_document_route_removes_graph_state(authenticated_client, monkeypatch):
    from app.api.v1.routes import documents as document_routes

    calls = {}

    class FakeDocumentService:
        async def archive_document(self, *_args, **_kwargs):
            calls["called"] = True
            return {
                "document_id": "doc_123",
                "namespace": "default",
                "status": "archived",
            }

    monkeypatch.setattr(document_routes, 'DocumentService', FakeDocumentService)

    response = await authenticated_client.post('/v1/documents/doc_123:archive')

    assert response.status_code == 200
    assert calls["called"] is True
    assert response.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_archive_canonical_document_uses_run_sync_for_graph_removal(monkeypatch):
    from app.services.document_service import DocumentService

    document = Document(
        document_id="doc_123",
        user_id="user_123",
        namespace="default",
        status="active",
        source_file_name="refund-policy.md",
    )

    class _Result:
        def scalar_one_or_none(self):
            return document

    sync_db = object()
    captured = {}

    class _Db:
        def __init__(self):
            self.sync_session = object()
            self.run_sync = AsyncMock()
            self.commit = AsyncMock()

        async def execute(self, *_args, **_kwargs):
            return _Result()

    db = _Db()

    async def _run_sync(fn):
        return fn(sync_db)

    db.run_sync.side_effect = _run_sync

    def fake_remove(self, passed_db, *, scope, document_id):
        captured["passed_db"] = passed_db
        captured["scope"] = scope
        captured["document_id"] = document_id

    monkeypatch.setattr("app.services.document_service.DocumentGraphService.remove_document_graph", fake_remove)

    payload = await DocumentService().archive_document(
        db,
        user_id="user_123",
        document_id="doc_123",
    )

    db.run_sync.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert captured["passed_db"] is sync_db
    assert captured["scope"].user_id == "user_123"
    assert captured["scope"].namespace == "default"
    assert captured["document_id"] == "doc_123"
    assert payload["status"] == "archived"
