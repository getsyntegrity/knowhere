from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.routes.jobs import _build_error_response
from app.services.messaging import message_handlers


class _DBContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_build_error_response_parses_stringified_error_details():
    job = SimpleNamespace(
        error_message="Failed to parse the PDF file",
        error_code="INVALID_ARGUMENT",
        job_id="job_123",
    )

    error = _build_error_response(
        job,
        {
            "error_details": '{"file_type": "pdf", "reason": "PARSING_FAILED"}',
        },
    )

    assert error is not None
    assert error.details == {
        "file_type": "pdf",
        "reason": "PARSING_FAILED",
    }


@pytest.mark.asyncio
async def test_handle_job_failure_normalizes_stringified_error_details(
    monkeypatch,
):
    fake_db = AsyncMock()
    finalize_job_failure = AsyncMock(return_value=True)

    monkeypatch.setattr(
        message_handlers,
        "get_db_context",
        lambda: _DBContext(fake_db),
    )
    monkeypatch.setattr(
        message_handlers._lifecycle_service,
        "finalize_job_failure",
        finalize_job_failure,
    )

    result = await message_handlers.handle_job_failure(
        {
            "job_id": "job_123",
            "message_type": "job_failure",
            "error_code": "INVALID_ARGUMENT",
            "error_message": "Failed to parse the PDF file",
            "metadata": {
                "refund_credits": True,
                "details": '{"file_type": "pdf", "reason": "PARSING_FAILED"}',
            },
        }
    )

    assert result == {
        "status": "success",
        "job_id": "job_123",
        "error_code": "INVALID_ARGUMENT",
        "error_message": "Failed to parse the PDF file",
    }
    finalize_job_failure.assert_awaited_once_with(
        db=fake_db,
        job_id="job_123",
        error_message="Failed to parse the PDF file",
        error_code="INVALID_ARGUMENT",
        error_details={
            "file_type": "pdf",
            "reason": "PARSING_FAILED",
        },
        should_refund=True,
    )
