from types import SimpleNamespace

import pytest

from app.services.messaging import message_handlers as handlers
from shared.models.schemas.messages import JobFailureMessage


class _DummyDbContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_handle_failure_forwards_request_id_to_lifecycle(monkeypatch):
    captured: dict = {}

    class _Lifecycle:
        async def finalize_job_failure(self, **kwargs):
            captured.update(kwargs)
            return True

    monkeypatch.setattr(handlers, "get_db_context", lambda: _DummyDbContext())
    monkeypatch.setattr(handlers, "JobLifecycleService", lambda: _Lifecycle())

    message = JobFailureMessage(
        job_id="job_123",
        error_message="boom",
        error_code="WORKER_ERROR",
        metadata={"request_id": "req_123"},
    )

    result = await handlers._handle_failure_async(message)

    assert result["status"] == "success"
    assert captured["request_id"] == "req_123"
    assert captured["job_id"] == "job_123"


@pytest.mark.asyncio
async def test_handle_failure_uses_none_request_id_when_missing(monkeypatch):
    captured: dict = {}

    class _Lifecycle:
        async def finalize_job_failure(self, **kwargs):
            captured.update(kwargs)
            return True

    monkeypatch.setattr(handlers, "get_db_context", lambda: _DummyDbContext())
    monkeypatch.setattr(handlers, "JobLifecycleService", lambda: _Lifecycle())

    message = JobFailureMessage(
        job_id="job_456",
        error_message="boom",
        error_code="WORKER_ERROR",
        metadata={},
    )

    result = await handlers._handle_failure_async(message)

    assert result["status"] == "success"
    assert captured["request_id"] is None
    assert captured["job_id"] == "job_456"
