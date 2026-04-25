from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support.runtime import get_contract_database_url


async def _create_contract_engine() -> AsyncEngine:
    return create_async_engine(get_contract_database_url(), future=True)


async def _count_jobs() -> int:
    engine = await _create_contract_engine()
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text("SELECT COUNT(*) FROM jobs"))
            return int(result.scalar_one())
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_should_create_a_waiting_file_job_for_an_authenticated_developer(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "file_name": "contract-upload.pdf",
        "data_id": "contract-job-file-upload",
    }

    async with developer_api_client_factory() as api_client:
        from shared.services.redis import JobInfoRedisService, JobMetadataService
        from shared.services.redis.redis_service_factory import RedisServiceFactory

        response = await api_client.post("/api/v1/jobs", json=payload)

        assert response.status_code == 200

        response_json: dict[str, object] = response.json()
        job_id = cast(str, response_json["job_id"])

        assert job_id.startswith("job_")
        assert response_json["status"] == "waiting-file"
        assert response_json["source_type"] == "file"
        assert response_json["namespace"] == payload["namespace"]
        assert response_json["data_id"] == payload["data_id"]
        assert response_json["document_id"] is None
        assert response_json["upload_url"]
        assert response_json["upload_headers"] == {"Content-Type": "application/pdf"}
        assert response_json["expires_in"]
        assert response_json["created_at"]

        engine = await _create_contract_engine()
        try:
            async with engine.begin() as connection:
                job_row = (
                    await connection.execute(
                        text(
                            """
                            SELECT
                                user_id,
                                job_type,
                                status,
                                source_type,
                                s3_key,
                                webhook_enabled,
                                job_metadata
                            FROM jobs
                            WHERE job_id = :job_id
                            """
                        ),
                        {"job_id": job_id},
                    )
                ).mappings().one()
        finally:
            await engine.dispose()

        job_metadata = cast(dict[str, object], job_row["job_metadata"])
        persisted_document_id = cast(str, job_metadata["document_id"])
        original_request = cast(dict[str, object], job_metadata["original_request"])

        assert job_row["user_id"] == "local-dev-user"
        assert job_row["job_type"] == "kb_management"
        assert job_row["status"] == "waiting-file"
        assert job_row["source_type"] == "file"
        assert job_row["s3_key"] == f"uploads/{job_id}.pdf"
        assert job_row["webhook_enabled"] is False
        assert persisted_document_id.startswith("doc_")
        assert job_metadata["namespace"] == payload["namespace"]
        assert job_metadata["source_type"] == "file"
        assert job_metadata["source_file_name"] == payload["file_name"]
        assert job_metadata["data_id"] == payload["data_id"]
        assert original_request["file_name"] == payload["file_name"]
        assert original_request["source_type"] == payload["source_type"]

        redis_service = RedisServiceFactory.get_service()
        metadata_service = JobMetadataService(redis_service)
        job_info_service = JobInfoRedisService(redis_service)

        cached_metadata = await metadata_service.get_metadata(job_id)
        cached_job_info = await job_info_service.get_job_info(job_id)

        assert cached_metadata is not None
        assert cached_job_info is not None
        assert cached_metadata["document_id"] == persisted_document_id
        assert cached_metadata["namespace"] == payload["namespace"]
        assert cached_metadata["source_type"] == "file"
        assert cached_metadata["source_file_name"] == payload["file_name"]
        assert cached_job_info["job_id"] == job_id
        assert cached_job_info["user_id"] == "local-dev-user"
        assert cached_job_info["job_type"] == "kb_management"
        assert cached_job_info["source_type"] == "file"
        assert cached_job_info["s3_key"] == f"uploads/{job_id}.pdf"
        assert cached_job_info["webhook_enabled"] is False


@pytest.mark.asyncio
async def test_should_return_invalid_argument_when_file_mode_job_is_missing_file_name(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "data_id": "contract-job-missing-file-name",
    }

    async with developer_api_client_factory() as api_client:
        response = await api_client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 400
    assert response.headers["x-request-id"]

    response_json: dict[str, object] = response.json()
    error = cast(dict[str, object], response_json["error"])
    details = cast(dict[str, object], error["details"])
    violations = cast(list[dict[str, object]], details["violations"])

    assert response_json["success"] is False
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["message"] == "file_name is required when source_type is 'file'"
    assert violations == [
        {
            "field": "file_name",
            "description": "Required for file source type",
        }
    ]
    assert await _count_jobs() == 0


@pytest.mark.asyncio
async def test_should_return_invalid_argument_when_file_mode_job_uses_an_unsupported_file_type(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "file_name": "contract-upload.exe",
        "data_id": "contract-job-unsupported-file-type",
    }

    async with developer_api_client_factory() as api_client:
        response = await api_client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 400
    assert response.headers["x-request-id"]

    response_json: dict[str, object] = response.json()
    error = cast(dict[str, object], response_json["error"])
    details = cast(dict[str, object], error["details"])
    violations = cast(list[dict[str, object]], details["violations"])

    assert response_json["success"] is False
    assert error["code"] == "INVALID_ARGUMENT"
    assert str(error["message"]).startswith(
        "Unsupported file type. Supported formats:"
    )
    assert violations == [
        {
            "field": "file_name",
            "description": "File type not supported",
        }
    ]
    assert await _count_jobs() == 0


@pytest.mark.asyncio
async def test_should_require_authorization_when_creating_a_job(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "file_name": "contract-upload.pdf",
        "data_id": "contract-job-missing-authorization",
    }

    async with api_client_factory() as api_client:
        response = await api_client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 401
    assert response.headers["x-request-id"]

    response_json: dict[str, object] = response.json()
    error = cast(dict[str, object], response_json["error"])

    assert response_json["success"] is False
    assert error["code"] == "UNAUTHENTICATED"
    assert error["message"] == "Authentication required. Provide Authorization header."
    assert "details" not in error
    assert await _count_jobs() == 0


@pytest.mark.asyncio
async def test_should_reject_a_malformed_authorization_header_when_creating_a_job(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    payload: dict[str, str] = {
        "namespace": "contract-jobs",
        "source_type": "file",
        "file_name": "contract-upload.pdf",
        "data_id": "contract-job-malformed-authorization",
    }

    async with api_client_factory() as api_client:
        api_client.headers.update({"Authorization": "bad-token"})
        response = await api_client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 401
    assert response.headers["x-request-id"]

    response_json: dict[str, object] = response.json()
    error = cast(dict[str, object], response_json["error"])

    assert response_json["success"] is False
    assert error["code"] == "UNAUTHENTICATED"
    assert error["message"] == "Invalid Authorization header format"
    assert "details" not in error
    assert await _count_jobs() == 0
