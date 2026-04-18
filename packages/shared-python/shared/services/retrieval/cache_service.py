from __future__ import annotations

import hashlib
from typing import Any

from loguru import logger

from shared.services.redis import RedisServiceFactory

_RETRIEVAL_CACHE_TTL_SECONDS = 300
_VERSION_FALLBACK = 0


def _namespace_version_key(*, user_id: str, namespace: str) -> str:
    return f"retrieval:version:{user_id}:{namespace}"


def _cache_shape_digest(*, query: str, top_k: int, exclude_document_ids: list[str], graph_enabled: bool) -> str:
    normalized_excludes = sorted(exclude_document_ids)
    payload = f"{query}|{top_k}|{graph_enabled}|{'|'.join(normalized_excludes)}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


async def get_retrieval_namespace_cache_version(*, user_id: str, namespace: str) -> int:
    redis_service = RedisServiceFactory.get_service()
    raw = await redis_service.get(_namespace_version_key(user_id=user_id, namespace=namespace), default=_VERSION_FALLBACK)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _VERSION_FALLBACK


async def bump_retrieval_namespace_cache_version(*, user_id: str, namespace: str) -> int:
    redis_service = RedisServiceFactory.get_service()
    current = await get_retrieval_namespace_cache_version(user_id=user_id, namespace=namespace)
    next_version = current + 1
    await redis_service.set(_namespace_version_key(user_id=user_id, namespace=namespace), next_version)
    return next_version


async def invalidate_retrieval_cache_namespaces(*, user_id: str, namespaces: list[str]) -> None:
    seen: set[str] = set()
    for namespace in namespaces:
        if not namespace or namespace in seen:
            continue
        seen.add(namespace)
        try:
            await bump_retrieval_namespace_cache_version(user_id=user_id, namespace=namespace)
        except Exception as exc:
            logger.warning(f"Failed to invalidate retrieval cache namespace (ignored): user_id={user_id}, namespace={namespace}, error={exc}")


def _query_cache_key(*, user_id: str, namespace: str, version: int, query: str, top_k: int, exclude_document_ids: list[str], graph_enabled: bool) -> str:
    digest = _cache_shape_digest(
        query=query,
        top_k=top_k,
        exclude_document_ids=exclude_document_ids,
        graph_enabled=graph_enabled,
    )
    return f"retrieval:query:{user_id}:{namespace}:v{version}:{digest}"


async def get_cached_retrieval_query_result(
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    graph_enabled: bool,
) -> dict[str, Any] | None:
    version = await get_retrieval_namespace_cache_version(user_id=user_id, namespace=namespace)
    redis_service = RedisServiceFactory.get_service()
    return await redis_service.get(
        _query_cache_key(
            user_id=user_id,
            namespace=namespace,
            version=version,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            graph_enabled=graph_enabled,
        ),
        default=None,
    )


async def set_cached_retrieval_query_result(
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    graph_enabled: bool,
    response: dict[str, Any],
) -> None:
    version = await get_retrieval_namespace_cache_version(user_id=user_id, namespace=namespace)
    redis_service = RedisServiceFactory.get_service()
    await redis_service.set(
        _query_cache_key(
            user_id=user_id,
            namespace=namespace,
            version=version,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            graph_enabled=graph_enabled,
        ),
        response,
        ex=_RETRIEVAL_CACHE_TTL_SECONDS,
    )
