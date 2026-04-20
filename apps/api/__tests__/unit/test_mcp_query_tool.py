import json

from httpx import ASGITransport, AsyncClient
import pytest
from starlette.routing import Route


def test_mcp_runtime_dependency_is_installed():
    from mcp.server.fastmcp import FastMCP

    assert FastMCP is not None


def test_api_app_mounts_mcp_streamable_http_endpoint():
    import main as app_main

    mcp_routes = [
        route
        for route in app_main.app.routes
        if isinstance(route, Route) and getattr(route, 'path', None) == '/mcp'
    ]

    assert mcp_routes


@pytest.mark.asyncio
async def test_mcp_streamable_http_endpoint_reaches_protocol_handler():
    import main as app_main

    test_app = app_main.create_app()
    mcp_server = test_app.state.retrieval_mcp_server

    async with mcp_server.session_manager.run():
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport,
            base_url='http://127.0.0.1:5005',
        ) as client:
            response = await client.get(
                '/mcp',
                headers={'accept': 'text/event-stream'},
            )

    assert response.status_code != 404
    assert 'Missing session ID' in response.text


@pytest.mark.asyncio
async def test_real_mcp_runtime_registers_and_calls_kb_query(monkeypatch):
    from app.mcp import retrieval_server

    async def fake_run_retrieval_query(**kwargs):
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

    async def fake_resolve_mcp_user_id(*, ctx, db):
        assert db == 'db_resource'
        return 'user_123'

    monkeypatch.setattr(retrieval_server, 'run_retrieval_query', fake_run_retrieval_query)
    monkeypatch.setattr(retrieval_server, 'resolve_mcp_user_id', fake_resolve_mcp_user_id)

    server = retrieval_server.create_retrieval_mcp_server(db_factory=lambda: 'db_resource')

    tools = await server.list_tools()
    assert any(tool.name == 'kb.query' for tool in tools)

    content_blocks = await server.call_tool(
        'kb.query',
        {
            'query': 'refund policy',
            'top_k': 5,
            'graph_enabled': False,
        },
    )
    response = json.loads(content_blocks[0].text)

    assert response['namespace'] == 'default'
    assert response['results'][0]['chunk_id'] == 'chunk_456'
    assert response['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'


@pytest.mark.asyncio
async def test_create_retrieval_mcp_server_registers_kb_query_tool(monkeypatch):
    from app.mcp import retrieval_server

    registered = {}

    class FakeServer:
        def __init__(self, name, instructions=None, **_kwargs):
            self.name = name
            self.instructions = instructions

        def tool(self, name=None, description=None, **_kwargs):
            def decorator(fn):
                registered['name'] = name
                registered['description'] = description
                registered['fn'] = fn
                return fn
            return decorator

    async def fake_run_retrieval_query(**kwargs):
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

    monkeypatch.setattr(retrieval_server, 'FastMCP', FakeServer)
    monkeypatch.setattr(retrieval_server, 'run_retrieval_query', fake_run_retrieval_query)

    captured_auth = {}

    async def fake_get_current_user_id(*, request, authorization, db):
        captured_auth['authorization'] = authorization
        captured_auth['db'] = db
        captured_auth['path'] = getattr(getattr(request, 'url', None), 'path', None)
        return 'user_123'

    monkeypatch.setattr(retrieval_server, 'get_current_user_id', fake_get_current_user_id)

    server = retrieval_server.create_retrieval_mcp_server(db_factory=lambda: object())

    assert server.name == 'knowhere-retrieval'
    assert registered['name'] == 'kb.query'
    assert 'Query the published knowledge base' in registered['description']

    class FakeRequestContext:
        def __init__(self):
            self.request = type(
                'Req',
                (),
                {
                    'headers': {'authorization': 'Bearer sk_test'},
                    'url': type('Url', (), {'path': '/mcp'})(),
                },
            )()

    class FakeContext:
        def __init__(self):
            self.request_context = FakeRequestContext()

    response = await registered['fn'](
        query='refund policy',
        namespace=None,
        top_k=5,
        exclude_document_ids=['doc_skip'],
        exclude_sections=[{'document_id': 'doc_123', 'section_path': 'Policies / Billing'}],
        graph_enabled=False,
        ctx=FakeContext(),
    )

    assert response['namespace'] == 'default'
    assert response['results'][0]['chunk_id'] == 'chunk_456'
    assert response['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'
    assert captured_auth['authorization'] == 'Bearer sk_test'
