import importlib
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from tests.support.contract_database import ContractDatabase


def _build_s3_event_payload(job_id: str) -> dict[str, object]:
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-west-1",
                "eventTime": "2026-04-26T00:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "knowhere-test-uploads"},
                    "object": {"key": f"uploads/{job_id}.pdf", "size": 256},
                },
            }
        ]
    }


async def _insert_waiting_file_job() -> tuple[str, str]:
    user_id = f"contract-s3-user-{uuid4().hex[:12]}"
    job_id = f"job_{uuid4().hex[:12]}"

    await ContractDatabase.insert_user(user_id=user_id)
    await ContractDatabase.insert_job(
        job_id=job_id,
        user_id=user_id,
        status="waiting-file",
        job_type="kb_management",
        source_type="file",
        s3_key=f"uploads/{job_id}.pdf",
    )

    return user_id, job_id


@pytest.mark.asyncio
async def test_should_acknowledge_an_sns_subscription_confirmation_request(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        response = await api_client.get(
            "/api/v1/internal/s3-events",
            headers={"x-amz-sns-message-type": "SubscriptionConfirmation"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "SNS subscription confirmed"}


@pytest.mark.asyncio
async def test_should_accept_a_direct_upload_complete_event_advance_the_waiting_job_and_start_workflow_handoff(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
    monkeypatch: MonkeyPatch,
) -> None:
    workflow_calls: list[dict[str, str | None]] = []
    user_id: str = ""
    job_id: str = ""

    class FakeKBOrchestrator:
        async def start_workflow(
            self,
            db,
            job_id: str,
            source_type: str,
            file_path: str | None,
            file_url: str | None,
            user_id: str,
        ) -> None:
            workflow_calls.append(
                {
                    "job_id": job_id,
                    "source_type": source_type,
                    "file_path": file_path,
                    "file_url": file_url,
                    "user_id": user_id,
                }
            )

    async with api_client_factory() as api_client:
        user_id, job_id = await _insert_waiting_file_job()
        s3_events_module = importlib.import_module("app.api.v1.routes.s3_events")
        monkeypatch.setattr(s3_events_module, "KBOrchestrator", FakeKBOrchestrator)
        response = await api_client.post(
            "/api/v1/internal/s3-events",
            json=_build_s3_event_payload(job_id),
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Event handled successfully"}

    job_row = await ContractDatabase.fetch_job(job_id)

    assert job_row is not None
    assert job_row["status"] == "pending"
    assert workflow_calls == [
        {
            "job_id": job_id,
            "source_type": "file",
            "file_path": None,
            "file_url": None,
            "user_id": user_id,
        }
    ]


@pytest.mark.asyncio
async def test_should_accept_an_sns_wrapped_upload_complete_event_and_advance_a_waiting_file_job(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
    monkeypatch: MonkeyPatch,
) -> None:
    job_id: str = ""

    class FakeKBOrchestrator:
        async def start_workflow(
            self,
            db,
            job_id: str,
            source_type: str,
            file_path: str | None,
            file_url: str | None,
            user_id: str,
        ) -> None:
            return None

    async with api_client_factory() as api_client:
        _, job_id = await _insert_waiting_file_job()
        s3_events_module = importlib.import_module("app.api.v1.routes.s3_events")
        monkeypatch.setattr(s3_events_module, "KBOrchestrator", FakeKBOrchestrator)
        response = await api_client.post(
            "/api/v1/internal/s3-events",
            content=json.dumps(
                {
                    "Type": "Notification",
                    "Message": json.dumps(_build_s3_event_payload(job_id)),
                }
            ).encode("utf-8"),
            headers={"x-amz-sns-message-type": "Notification"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Event handled successfully"}

    job_row = await ContractDatabase.fetch_job(job_id)

    assert job_row is not None
    assert job_row["status"] == "pending"


@pytest.mark.asyncio
async def test_should_return_ok_for_a_malformed_event_payload_without_triggering_retries(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        response = await api_client.post(
            "/api/v1/internal/s3-events",
            content=b"{this-is-not-valid-json",
        )

    assert response.status_code == 200
    response_json = cast(dict[str, object], response.json())
    assert response_json["message"] == "Event handled successfully"
