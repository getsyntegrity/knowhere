import builtins
import importlib
import json
import sys

from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
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
            response = await client.post(
                '/mcp',
                headers={
                    'accept': 'application/json, text/event-stream',
                    'content-type': 'application/json',
                },
                json={
                    'jsonrpc': '2.0',
                    'id': 1,
                    'method': 'initialize',
                    'params': {
                        'protocolVersion': '2025-11-25',
                        'capabilities': {},
                        'clientInfo': {
                            'name': 'codex-test',
                            'version': '0.1.0',
                        },
                    },
                },
            )

    assert response.status_code == 200
    assert '"name":"knowhere-retrieval"' in response.text
    assert response.headers.get('mcp-session-id') is None


@pytest.mark.asyncio
async def test_mcp_streamable_http_endpoint_initializes_with_public_host():
    import main as app_main

    test_app = app_main.create_app()
    mcp_server = test_app.state.retrieval_mcp_server

    async with mcp_server.session_manager.run():
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport,
            base_url='https://api-staging.knowhereto.ai',
        ) as http_client:
            async with streamable_http_client(
                'https://api-staging.knowhereto.ai/mcp',
                http_client=http_client,
            ) as (read_stream, write_stream, get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    result = await session.initialize()

    assert result.serverInfo.name == 'knowhere-retrieval'
    assert get_session_id() is None


@pytest.mark.asyncio
async def test_mcp_streamable_http_endpoint_handles_follow_up_requests_without_sticky_sessions():
    import main as app_main

    test_app = app_main.create_app()
    mcp_server = test_app.state.retrieval_mcp_server

    async with mcp_server.session_manager.run():
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport,
            base_url='https://api-staging.knowhereto.ai',
        ) as client:
            initialize_response = await client.post(
                '/mcp',
                headers={
                    'accept': 'application/json, text/event-stream',
                    'content-type': 'application/json',
                },
                json={
                    'jsonrpc': '2.0',
                    'id': 1,
                    'method': 'initialize',
                    'params': {
                        'protocolVersion': '2025-11-25',
                        'capabilities': {},
                        'clientInfo': {
                            'name': 'codex-test',
                            'version': '0.1.0',
                        },
                    },
                },
            )
            tools_response = await client.post(
                '/mcp',
                headers={
                    'accept': 'application/json, text/event-stream',
                    'content-type': 'application/json',
                    'mcp-session-id': 'cross-pod-session-id',
                },
                json={
                    'jsonrpc': '2.0',
                    'id': 2,
                    'method': 'tools/list',
                    'params': {},
                },
            )

    assert initialize_response.status_code == 200
    assert tools_response.status_code == 200
    assert '"name":"kb.query"' in tools_response.text


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
                },
                {
                    'document_id': 'doc_123',
                    'chunk_id': 'chunk_789',
                    'section_id': 'sec_12',
                    'section_path': 'Policies / Billing / Refunds',
                    'source_file_name': 'refund-policy.md',
                    'chunk_type': 'image',
                    'content': 'Image showing the refund policy table.',
                    'score': 0.9,
                    'asset_url': 'https://assets.test/refund-policy/page-1.png?signature=fresh',
                    'citation': {
                        'document_id': 'doc_123',
                        'chunk_id': 'chunk_789',
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
    query_tool = next(tool for tool in tools if tool.name == 'kb.query')
    assert query_tool.description == 'Search for information and return relevant knowledge snippets.'
    assert query_tool.inputSchema['properties'] == {
        'query': {
            'description': 'What you want to search for.',
            'title': 'Query',
            'type': 'string',
        },
        'top_k': {
            'default': 5,
            'description': 'Maximum number of results to return.',
            'title': 'Top K',
            'type': 'integer',
        },
    }
    assert query_tool.inputSchema['required'] == ['query']

    content_blocks = await server.call_tool(
        'kb.query',
        {
            'query': 'refund policy',
            'top_k': 5,
        },
    )
    response = json.loads(content_blocks[0].text)

    assert response == {
        'query': 'refund policy',
        'results': [
            {
                'content': 'Annual plans may be refunded within 30 days of purchase...',
                'source_file_name': 'refund-policy.md',
                'section_path': 'Policies / Billing / Refunds',
                'chunk_type': 'text',
            },
            {
                'content': 'Image showing the refund policy table.',
                'source_file_name': 'refund-policy.md',
                'section_path': 'Policies / Billing / Refunds',
                'chunk_type': 'image',
                'asset_url': 'https://assets.test/refund-policy/page-1.png?signature=fresh',
            }
        ],
    }
    assert 'chunk_id' not in response['results'][0]
    assert 'score' not in response['results'][0]
    assert 'citation' not in response['results'][0]
    assert captured['namespace'] == 'default'
    assert captured['exclude_document_ids'] == []
    assert captured['exclude_sections'] == []


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
            self.kwargs = _kwargs

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
    assert server.instructions == (
        'Use this server to search knowledge. '
        'If you need information before answering, try searching with this tool.'
    )
    assert server.kwargs['stateless_http'] is True
    assert server.kwargs['transport_security'].enable_dns_rebinding_protection is False
    assert registered['name'] == 'kb.query'
    assert registered['description'] == 'Search for information and return relevant knowledge snippets.'

    class FakeRequestContext:
        def __init__(self):
            self.request = type(
                'Req',
                (),
                {
                    'headers': {
                        'Authorization': 'Bearer sk_test',
                        'X-Knowhere-Namespace': 'enterprise',
                    },
                    'url': type('Url', (), {'path': '/mcp'})(),
                },
            )()

    class FakeContext:
        def __init__(self):
            self.request_context = FakeRequestContext()

    response = await registered['fn'](
        query='refund policy',
        top_k=5,
        ctx=FakeContext(),
    )

    assert response == {
        'query': 'refund policy',
        'results': [
            {
                'content': 'Annual plans may be refunded within 30 days of purchase...',
                'source_file_name': 'refund-policy.md',
                'section_path': 'Policies / Billing / Refunds',
                'chunk_type': 'text',
            }
        ],
    }
    assert captured_auth['authorization'] == 'Bearer sk_test'
    assert captured['namespace'] == 'enterprise'
    assert captured['exclude_document_ids'] == []
    assert captured['exclude_sections'] == []


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
            top_k=5,
            ctx=None,
        )
