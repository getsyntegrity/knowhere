from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, cast

import pytest
from httpx import AsyncClient

from tests.support.contract_database import ContractDatabase


DEMO_SOURCE_ID = "demo-tsla-q4-2025"


@pytest.mark.asyncio
async def test_should_return_demo_catalog_with_resolvable_canonical_citations(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        catalog_response = await api_client.get("/api/v1/demo/catalog")

    assert catalog_response.status_code == 200
    catalog = cast(dict[str, Any], catalog_response.json())
    sources = cast(list[dict[str, Any]], catalog["sources"])
    source = sources[0]
    examples = cast(list[dict[str, Any]], source["examples"])
    citations = cast(list[dict[str, Any]], examples[0]["citations"])
    citation = citations[0]

    assert source["demo_source_id"] == DEMO_SOURCE_ID
    assert source["canonical_document_id"] == "demo-doc-tsla-q4-2025"
    assert source["chunk_count"] == 70
    assert source["original_file"]["can_download"] is False
    assert citation["canonical_document_id"] == "demo-doc-tsla-q4-2025"
    assert citation["canonical_chunk_id"].startswith(f"{DEMO_SOURCE_ID}:")

    async with api_client_factory() as api_client:
        chunks_response = await api_client.get(
            f"/api/v1/demo/sources/{DEMO_SOURCE_ID}/chunks?page_size=200"
        )
        chunk_response = await api_client.get(
            "/api/v1/demo/sources/"
            f"{DEMO_SOURCE_ID}/chunks/{citation['canonical_chunk_id']}"
        )

    assert chunks_response.status_code == 200
    assert chunk_response.status_code == 200
    chunks_body = cast(dict[str, Any], chunks_response.json())
    chunk_page = cast(list[dict[str, Any]], chunks_body["chunks"])
    asset_url = next(
        str(chunk["asset_url"]) for chunk in chunk_page if chunk.get("asset_url")
    )
    chunk_body = cast(dict[str, Any], chunk_response.json())
    chunk = cast(dict[str, Any], chunk_body["chunk"])

    assert chunk["id"] == citation["canonical_chunk_id"]
    assert citation["content"] in chunk["content"]

    async with api_client_factory() as api_client:
        asset_response = await api_client.get(asset_url)

    assert asset_response.status_code == 200


@pytest.mark.asyncio
async def test_should_materialize_demo_source_without_parse_or_credit_charge(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        first_response = await api_client.post(
            "/api/v1/demo/materializations",
            json={
                "namespace": "contract-demo",
                "demo_source_ids": [DEMO_SOURCE_ID],
            },
        )
        retry_response = await api_client.post(
            "/api/v1/demo/materializations",
            json={
                "namespace": "contract-demo",
                "demo_source_ids": [DEMO_SOURCE_ID],
            },
        )
        retrieval_response = await api_client.post(
            "/api/v1/retrieval/query",
            json={
                "namespace": "contract-demo",
                "query": "xAI investment",
                "top_k": 5,
            },
        )

    assert first_response.status_code == 200
    assert retry_response.status_code == 200
    assert retrieval_response.status_code == 200

    first_source = cast(dict[str, Any], first_response.json()["sources"][0])
    retry_source = cast(dict[str, Any], retry_response.json()["sources"][0])
    document_id = str(first_source["document_id"])

    assert first_source["status"] == "created"
    assert retry_source["status"] == "existing"
    assert retry_source["document_id"] == document_id

    materialization_rows = await ContractDatabase.fetch_all(
        """
        SELECT demo_source_id, document_id
        FROM demo_materializations
        WHERE user_id = 'local-dev-user'
          AND namespace = 'contract-demo'
          AND demo_source_id = :demo_source_id
        """,
        {"demo_source_id": DEMO_SOURCE_ID},
    )
    document_row = await ContractDatabase.fetch_one(
        """
        SELECT document_id, status, source_file_name
        FROM documents
        WHERE document_id = :document_id
        """,
        {"document_id": document_id},
    )
    chunk_rows = await ContractDatabase.fetch_all(
        """
        SELECT id
        FROM document_chunks
        WHERE document_id = :document_id
        """,
        {"document_id": document_id},
    )
    job_rows = await ContractDatabase.fetch_all(
        """
        SELECT status, job_type, credits_charged, billing_status
        FROM jobs
        WHERE user_id = 'local-dev-user'
          AND job_metadata ->> 'demo_source_id' = :demo_source_id
        """,
        {"demo_source_id": DEMO_SOURCE_ID},
    )

    assert materialization_rows == [
        {"demo_source_id": DEMO_SOURCE_ID, "document_id": document_id}
    ]
    assert document_row == {
        "document_id": document_id,
        "status": "active",
        "source_file_name": "TSLA-Q4-2025-Update.pdf",
    }
    assert len(chunk_rows) == 70
    assert job_rows == [
        {
            "status": "done",
            "job_type": "demo_materialization",
            "credits_charged": 0,
            "billing_status": "skipped",
        }
    ]

    retrieval_body = cast(dict[str, Any], retrieval_response.json())
    retrieval_results = cast(list[dict[str, Any]], retrieval_body["results"])

    assert retrieval_body["namespace"] == "contract-demo"
    assert retrieval_results
    assert retrieval_results[0]["source"]["document_id"] == document_id
