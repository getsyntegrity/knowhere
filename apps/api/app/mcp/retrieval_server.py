from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_id
from shared.core.database import get_db_context
from shared.services.retrieval import run_retrieval_query

try:
    from mcp.server.fastmcp import Context, FastMCP
except ImportError:  # pragma: no cover - optional until MCP deps are installed
    FastMCP = None
    Context = object  # type: ignore[assignment]


DbFactory = Callable[[], AsyncIterator[AsyncSession] | AsyncSession | object]


@asynccontextmanager
async def _db_context_from_factory(db_factory: DbFactory):
    resource = db_factory()
    if hasattr(resource, '__aenter__') and hasattr(resource, '__aexit__'):
        async with resource as db:
            yield db
        return
    if hasattr(resource, '__aiter__'):
        async for db in resource:
            yield db
            break
        return
    yield resource


async def resolve_mcp_user_id(*, ctx: Context | None, db: AsyncSession) -> str:
    request_context = getattr(ctx, 'request_context', None)
    request = getattr(request_context, 'request', None)
    if request is None:
        raise RuntimeError('MCP auth context request is not available')

    headers = getattr(request, 'headers', {}) or {}
    authorization = headers.get('authorization')
    return await get_current_user_id(
        request=request,
        authorization=authorization,
        db=db,
    )


def create_retrieval_mcp_server(*, db_factory: DbFactory = get_db_context):
    if FastMCP is None:
        raise RuntimeError('mcp dependency is not installed')

    server = FastMCP(
        'knowhere-retrieval',
        instructions='Query the published knowledge base through the shared retrieval service.',
    )

    @server.tool(
        name='kb.query',
        description='Query the published knowledge base and return canonical retrieval results.',
    )
    async def kb_query(
        query: str,
        namespace: str | None = None,
        top_k: int = 10,
        exclude_document_ids: list[str] | None = None,
        exclude_sections: list[dict[str, str]] | None = None,
        graph_enabled: bool = False,
        ctx: Context | None = None,
    ) -> dict:
        effective_namespace = namespace or 'default'
        async with _db_context_from_factory(db_factory) as db:
            user_id = await resolve_mcp_user_id(ctx=ctx, db=db)
            return await run_retrieval_query(
                db=db,
                user_id=user_id,
                namespace=effective_namespace,
                query=query,
                top_k=top_k,
                exclude_document_ids=exclude_document_ids or [],
                exclude_sections=exclude_sections or [],
                graph_enabled=graph_enabled,
            )

    return server
