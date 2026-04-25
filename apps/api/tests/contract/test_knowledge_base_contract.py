from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support.runtime import get_contract_database_url


async def _create_contract_engine() -> AsyncEngine:
    return create_async_engine(get_contract_database_url(), future=True)


async def _fetch_directory_by_title(title: str) -> dict[str, object] | None:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        id,
                        title,
                        parent_id,
                        user_id
                    FROM file_directory
                    WHERE title = :title
                    LIMIT 1
                    """
                ),
                {"title": title},
            )
            directory_row = result.mappings().first()
            return dict(directory_row) if directory_row is not None else None
    finally:
        await engine.dispose()


async def _count_directories_by_title(title: str) -> int:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM file_directory
                    WHERE title = :title
                    """
                ),
                {"title": title},
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _insert_directory(
    *,
    directory_id: str,
    title: str,
    user_id: str = "local-dev-user",
    parent_id: str | None = None,
) -> None:
    engine = await _create_contract_engine()
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO file_directory (
                        id,
                        title,
                        parent_id,
                        user_id,
                        create_time,
                        update_time
                    ) VALUES (
                        :id,
                        :title,
                        :parent_id,
                        :user_id,
                        :create_time,
                        :update_time
                    )
                    """
                ),
                {
                    "id": directory_id,
                    "title": title,
                    "parent_id": parent_id,
                    "user_id": user_id,
                    "create_time": timestamp,
                    "update_time": timestamp,
                },
            )
    finally:
        await engine.dispose()


async def _insert_knowledge_base_content(
    *,
    content_id: str,
    path: str,
    content: str,
) -> None:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO knowledge_base (
                        id,
                        content,
                        path,
                        type,
                        length,
                        keywords,
                        summary,
                        know_id,
                        tokens,
                        embedding
                    ) VALUES (
                        :id,
                        :content,
                        :path,
                        :type,
                        :length,
                        :keywords,
                        :summary,
                        :know_id,
                        :tokens,
                        :embedding
                    )
                    """
                ),
                {
                    "id": content_id,
                    "content": content,
                    "path": path,
                    "type": "PTXT",
                    "length": len(content),
                    "keywords": "contract",
                    "summary": "summary",
                    "know_id": "know_contract",
                    "tokens": "contract tokens",
                    "embedding": "",
                },
            )
    finally:
        await engine.dispose()


async def _count_knowledge_base_rows(content_id: str) -> int:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM knowledge_base
                    WHERE id = :content_id
                    """
                ),
                {"content_id": content_id},
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_should_create_a_default_root_directory_on_first_directory_tree_access(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        response = await api_client.post("/api/v1/kb/get_directory")

    assert response.status_code == 201

    response_json = cast(list[dict[str, object]], response.json())
    root_directory = await _fetch_directory_by_title("Default Directory")

    assert len(response_json) == 1
    assert response_json[0]["title"] == "Default Directory"
    assert response_json[0]["parent_id"] is None
    assert response_json[0]["children"] == []
    assert root_directory is not None
    assert root_directory["user_id"] == "local-dev-user"


@pytest.mark.asyncio
async def test_should_create_a_directory_for_the_authenticated_user(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    title = f"contract-directory-{uuid4().hex[:8]}"

    async with developer_api_client_factory() as api_client:
        response = await api_client.post(
            "/api/v1/kb/create_directory",
            json={"title": title, "parent_id": None, "user_id": "ignored"},
        )

    assert response.status_code == 201
    assert response.json() == {"message": "Directory created"}

    created_directory = await _fetch_directory_by_title(title)

    assert created_directory is not None
    assert created_directory["title"] == title
    assert created_directory["user_id"] == "local-dev-user"
    assert created_directory["parent_id"] is None


@pytest.mark.asyncio
async def test_should_delete_a_directory_and_remove_it_from_subsequent_tree_reads(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    title = f"contract-delete-{uuid4().hex[:8]}"

    async with developer_api_client_factory() as api_client:
        create_response = await api_client.post(
            "/api/v1/kb/create_directory",
            json={"title": title, "parent_id": None, "user_id": "ignored"},
        )
        created_directory = await _fetch_directory_by_title(title)
        assert create_response.status_code == 201
        assert created_directory is not None

        delete_response = await api_client.post(
            "/api/v1/kb/delete_directory",
            json={
                "id": created_directory["id"],
                "title": title,
                "parent_id": None,
                "user_id": "ignored",
            },
        )
        tree_response = await api_client.post("/api/v1/kb/get_directory")

    assert delete_response.status_code == 201
    assert delete_response.json() == {"message": "Directory deleted"}

    tree_response_json = cast(list[dict[str, object]], tree_response.json())

    assert await _count_directories_by_title(title) == 0
    assert all(directory["title"] != title for directory in tree_response_json)


@pytest.mark.asyncio
async def test_should_return_invalid_argument_when_updating_a_directory_without_an_id(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        response = await api_client.post(
            "/api/v1/kb/update_directory",
            json={"title": "renamed-directory"},
        )

    assert response.status_code == 400
    assert response.headers["x-request-id"]

    response_json = cast(dict[str, object], response.json())
    error = cast(dict[str, object], response_json["error"])
    details = cast(dict[str, object], error["details"])
    violations = cast(list[dict[str, object]], details["violations"])

    assert response_json["success"] is False
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["message"] == "Directory id is required"
    assert violations == [
        {
            "field": "id",
            "description": "Directory id is required for updates",
        }
    ]


@pytest.mark.asyncio
async def test_should_persist_updated_directory_attributes(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    initial_title = f"contract-update-{uuid4().hex[:8]}"
    updated_title = f"{initial_title}-renamed"

    async with developer_api_client_factory() as api_client:
        create_response = await api_client.post(
            "/api/v1/kb/create_directory",
            json={"title": initial_title, "parent_id": None, "user_id": "ignored"},
        )
        created_directory = await _fetch_directory_by_title(initial_title)
        assert create_response.status_code == 201
        assert created_directory is not None

        update_response = await api_client.post(
            "/api/v1/kb/update_directory",
            json={
                "id": created_directory["id"],
                "title": updated_title,
                "parent_id": None,
            },
        )

    assert update_response.status_code == 201
    assert update_response.json() == {"message": "Directory updated"}

    updated_directory = await _fetch_directory_by_title(updated_title)

    assert updated_directory is not None
    assert updated_directory["id"] == created_directory["id"]


@pytest.mark.asyncio
async def test_should_list_content_for_the_selected_directory(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    directory_id = f"dir_{uuid4().hex[:12]}"
    directory_title = f"contract-list-{uuid4().hex[:8]}"
    content_id = f"kb_{uuid4().hex[:12]}"

    async with developer_api_client_factory() as api_client:
        await _insert_directory(directory_id=directory_id, title=directory_title)
        await _insert_knowledge_base_content(
            content_id=content_id,
            path=f"{directory_title};contract-file.pdf;1. Introduction",
            content="Contract content",
        )
        response = await api_client.post(
            "/api/v1/kb/list_directory",
            json={"id": directory_id},
        )

    assert response.status_code == 201

    response_json = cast(list[dict[str, object]], response.json())

    assert len(response_json) == 1
    assert response_json[0]["id"] == content_id
    assert response_json[0]["path"] == f"{directory_title};contract-file.pdf;1. Introduction"
    assert response_json[0]["content"] == "Contract content"


@pytest.mark.asyncio
async def test_should_create_a_root_knowledge_base_path(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    path = f"contract-root-{uuid4().hex[:8]}"

    async with developer_api_client_factory() as api_client:
        response = await api_client.post(
            "/api/v1/kb/add_kb",
            json={"path": path},
        )

    assert response.status_code == 201
    assert response.json() == {"message": "Knowledge-base path added"}

    created_directory = await _fetch_directory_by_title(path)

    assert created_directory is not None
    assert created_directory["user_id"] == "local-dev-user"
    assert created_directory["parent_id"] is None


@pytest.mark.asyncio
async def test_should_delete_a_directory_through_the_contents_route_when_the_id_is_a_directory(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    directory_id = f"dir_{uuid4().hex[:12]}"
    directory_title = f"contract-content-dir-{uuid4().hex[:8]}"

    async with developer_api_client_factory() as api_client:
        await _insert_directory(
            directory_id=directory_id,
            title=directory_title,
        )
        response = await api_client.delete(f"/api/v1/kb/contents/{directory_id}")

    assert response.status_code == 200
    assert response.json() == {"message": "Directory deleted"}
    assert await _count_directories_by_title(directory_title) == 0


@pytest.mark.asyncio
async def test_should_delete_knowledge_base_content_through_the_contents_route_when_the_id_is_content(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    content_id = f"kb_{uuid4().hex[:12]}"

    async with developer_api_client_factory() as api_client:
        await _insert_knowledge_base_content(
            content_id=content_id,
            path="contract-content;contract-file.pdf;1. Introduction",
            content="Delete me",
        )
        response = await api_client.delete(f"/api/v1/kb/contents/{content_id}")

    assert response.status_code == 200
    assert response.json() == {"message": "Content deleted"}
    assert await _count_knowledge_base_rows(content_id) == 0
