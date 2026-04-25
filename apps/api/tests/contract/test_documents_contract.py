from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support.runtime import get_contract_database_url


async def _create_contract_engine() -> AsyncEngine:
    return create_async_engine(get_contract_database_url(), future=True)


async def _insert_user(user_id: str) -> None:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO "user" (id, name, email)
                    VALUES (:user_id, :name, :email)
                    """
                ),
                {
                    "user_id": user_id,
                    "name": f"Contract User {user_id}",
                    "email": f"{user_id}@contract.knowhere.local",
                },
            )
    finally:
        await engine.dispose()


async def _insert_document(
    *,
    document_id: str,
    user_id: str = "local-dev-user",
    namespace: str = "contract-documents",
    status: str = "active",
    source_file_name: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    engine = await _create_contract_engine()
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    effective_updated_at = updated_at or timestamp

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        document_id,
                        user_id,
                        namespace,
                        status,
                        current_job_result_id,
                        source_file_name,
                        created_at,
                        updated_at,
                        archived_at
                    ) VALUES (
                        :document_id,
                        :user_id,
                        :namespace,
                        :status,
                        :current_job_result_id,
                        :source_file_name,
                        :created_at,
                        :updated_at,
                        :archived_at
                    )
                    """
                ),
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "namespace": namespace,
                    "status": status,
                    "current_job_result_id": None,
                    "source_file_name": source_file_name or f"{document_id}.pdf",
                    "created_at": timestamp,
                    "updated_at": effective_updated_at,
                    "archived_at": (
                        effective_updated_at if status == "archived" else None
                    ),
                },
            )
    finally:
        await engine.dispose()


async def _fetch_document(document_id: str) -> dict[str, object]:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            document_row = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            document_id,
                            user_id,
                            namespace,
                            status,
                            current_job_result_id,
                            source_file_name,
                            archived_at
                        FROM documents
                        WHERE document_id = :document_id
                        """
                    ),
                    {"document_id": document_id},
                )
            ).mappings().one()
            return dict(document_row)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_should_list_only_the_authenticated_users_documents_for_the_effective_namespace(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        other_user_id = f"contract-user-{uuid4().hex[:12]}"
        await _insert_user(other_user_id)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        owned_first_document_id = f"doc_{uuid4().hex[:12]}"
        owned_second_document_id = f"doc_{uuid4().hex[:12]}"
        await _insert_document(
            document_id=owned_first_document_id,
            updated_at=now - timedelta(minutes=5),
        )
        await _insert_document(
            document_id=owned_second_document_id,
            updated_at=now,
        )
        await _insert_document(
            document_id=f"doc_{uuid4().hex[:12]}",
            namespace="other-namespace",
        )
        await _insert_document(
            document_id=f"doc_{uuid4().hex[:12]}",
            user_id=other_user_id,
        )
        await _insert_document(
            document_id=f"doc_{uuid4().hex[:12]}",
            status="archived",
        )

        default_namespace_response = await api_client.get("/api/v1/documents")
        named_namespace_response = await api_client.get(
            "/api/v1/documents",
            params={"namespace": "contract-documents"},
        )

    assert default_namespace_response.status_code == 200
    assert named_namespace_response.status_code == 200

    default_namespace_json = cast(dict[str, object], default_namespace_response.json())
    named_namespace_json = cast(dict[str, object], named_namespace_response.json())
    documents = cast(list[dict[str, object]], named_namespace_json["documents"])

    assert default_namespace_json == {
        "namespace": "default",
        "documents": [],
    }
    assert named_namespace_json["namespace"] == "contract-documents"
    assert [document["document_id"] for document in documents] == [
        owned_second_document_id,
        owned_first_document_id,
    ]
    assert all(document["namespace"] == "contract-documents" for document in documents)
    assert all(document["status"] == "active" for document in documents)


@pytest.mark.asyncio
async def test_should_return_document_details_for_an_owned_document(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    document_id = f"doc_{uuid4().hex[:12]}"

    async with developer_api_client_factory() as api_client:
        await _insert_document(
            document_id=document_id,
            source_file_name="contract-detail.pdf",
        )
        response = await api_client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())

    assert response_json["document_id"] == document_id
    assert response_json["namespace"] == "contract-documents"
    assert response_json["status"] == "active"
    assert response_json["current_job_result_id"] is None
    assert response_json["source_file_name"] == "contract-detail.pdf"
    assert response_json["created_at"]
    assert response_json["updated_at"]
    assert response_json["archived_at"] is None


@pytest.mark.asyncio
async def test_should_return_not_found_when_requesting_a_missing_document(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    missing_document_id = f"doc_{uuid4().hex[:12]}"

    async with developer_api_client_factory() as api_client:
        response = await api_client.get(f"/api/v1/documents/{missing_document_id}")

    assert response.status_code == 404
    assert response.headers["x-request-id"]

    response_json = cast(dict[str, object], response.json())
    error = cast(dict[str, object], response_json["error"])

    assert response_json["success"] is False
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "Document not found"
    assert error["details"] == {
        "resource": "Document",
        "id": missing_document_id,
    }


@pytest.mark.asyncio
async def test_should_archive_a_document_via_the_canonical_archive_route(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    document_id = f"doc_{uuid4().hex[:12]}"

    async with developer_api_client_factory() as api_client:
        await _insert_document(document_id=document_id)
        response = await api_client.post(f"/api/v1/documents/{document_id}/archive")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())
    persisted_document = await _fetch_document(document_id)

    assert response_json["document_id"] == document_id
    assert response_json["status"] == "archived"
    assert response_json["archived_at"]
    assert persisted_document["status"] == "archived"
    assert persisted_document["archived_at"] is not None


@pytest.mark.asyncio
async def test_should_archive_a_document_via_the_legacy_archive_route(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    document_id = f"doc_{uuid4().hex[:12]}"

    async with developer_api_client_factory() as api_client:
        await _insert_document(document_id=document_id)
        response = await api_client.post(f"/api/v1/documents/{document_id}:archive")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())
    persisted_document = await _fetch_document(document_id)

    assert response_json["document_id"] == document_id
    assert response_json["status"] == "archived"
    assert response_json["archived_at"]
    assert persisted_document["status"] == "archived"
    assert persisted_document["archived_at"] is not None
