import builtins
import importlib
import json
import sys

from httpx import ASGITransport, AsyncClient
import pytest
from starlette.routing import Route


def test_mcp_runtime_dependency_is_installed():
    from mcp.server.fastmcp import FastMCP

    assert FastMCP is not None


def test_retrieval_server_import_fails_when_mcp_dependency_is_missing(monkeypatch):
    real_import = builtins.__import__
    original_module = sys.modules.pop('app.mcp.retrieval_server', None)

    def reject_mcp_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith('mcp'):
            raise ImportError('simulated missing mcp dependency')
        return real_import(name, globals, locals, fromlist, level)

    try:
        monkeypatch.setattr(builtins, '__import__', reject_mcp_import)

        with pytest.raises(ImportError, match='simulated missing mcp dependency'):
            importlib.import_module('app.mcp.retrieval_server')
    finally:
        sys.modules.pop('app.mcp.retrieval_server', None)
        if original_module is not None:
            sys.modules['app.mcp.retrieval_server'] = original_module


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

    captured = {}

    class FakeDbContext:
        async def __aenter__(self):
            return 'db_resource'

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def fake_run_retrieval_query(**kwargs):
        captured.update(kwargs)
        return {
            'namespace': kwargs['namespace'],
            'query': kwargs['query'],
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

    server = retrieval_server.create_retrieval_mcp_server(db_factory=FakeDbContext)

    tools = await server.list_tools()
    assert any(tool.name == 'kb.query' for tool in tools)

    content_blocks = await server.call_tool(
        'kb.query',
        {
            'query': 'refund policy',
            'top_k': 5,
        },
    )
    response = json.loads(content_blocks[0].text)

    assert response['namespace'] == 'default'
    assert response['results'][0]['chunk_id'] == 'chunk_456'
    assert response['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'


@pytest.mark.asyncio
async def test_real_mcp_runtime_exposes_only_kb_query_tool():
    from app.mcp import retrieval_server

    class FakeDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    server = retrieval_server.create_retrieval_mcp_server(db_factory=FakeDbContext)

    tools = await server.list_tools()

    assert [tool.name for tool in tools] == ['kb.query']


@pytest.mark.asyncio
async def test_create_retrieval_mcp_server_registers_kb_query_tool(monkeypatch):
    from app.mcp import retrieval_server

    registered = {}
    captured = {}

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

    class FakeDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def fake_run_retrieval_query(**kwargs):
        captured.update(kwargs)
        return {
            'namespace': kwargs['namespace'],
            'query': kwargs['query'],
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

    server = retrieval_server.create_retrieval_mcp_server(db_factory=FakeDbContext)

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
        ctx=FakeContext(),
    )

    assert response['namespace'] == 'default'
    assert response['results'][0]['chunk_id'] == 'chunk_456'
    assert response['results'][0]['content'] == 'Annual plans may be refunded within 30 days of purchase...'
    assert captured_auth['authorization'] == 'Bearer sk_test'


@pytest.mark.asyncio
async def test_kb_query_requires_db_factory_to_return_async_context_manager(monkeypatch):
    from app.mcp import retrieval_server

    registered = {}

    class FakeServer:
        def __init__(self, name, instructions=None, **_kwargs):
            self.name = name
            self.instructions = instructions

        def tool(self, name=None, description=None, **_kwargs):
            def decorator(fn):
                registered['fn'] = fn
                return fn
            return decorator

    monkeypatch.setattr(retrieval_server, 'FastMCP', FakeServer)

    async def fake_resolve_mcp_user_id(**_kwargs):
        pytest.fail('resolve_mcp_user_id should not be reached')

    monkeypatch.setattr(retrieval_server, 'resolve_mcp_user_id', fake_resolve_mcp_user_id)

    server = retrieval_server.create_retrieval_mcp_server(db_factory=lambda: object())

    assert server.name == 'knowhere-retrieval'

    with pytest.raises(TypeError, match='asynchronous context manager'):
        await registered['fn'](
            query='refund policy',
            namespace=None,
            top_k=5,
            exclude_document_ids=None,
            exclude_sections=None,
            ctx=None,
        )
