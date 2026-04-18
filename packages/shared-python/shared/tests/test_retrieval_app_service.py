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
