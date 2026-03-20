from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.services.messaging import message_handlers
from shared.core.state_machine.states import JobStatus
from shared.models.schemas.messages import JobStatusUpdateMessage


@asynccontextmanager
async def _fake_db_context():
    yield AsyncMock()


@pytest.mark.asyncio
async def test_handle_status_update_ignores_invalid_transition(monkeypatch):
    monkeypatch.setattr(message_handlers, "get_db_context", _fake_db_context)

    get_current_state = AsyncMock(return_value=JobStatus.WAITING_FILE.value)
    transition = AsyncMock()
    monkeypatch.setattr(message_handlers._state_machine, "get_current_state", get_current_state)
    monkeypatch.setattr(message_handlers._state_machine, "transition", transition)

    message = JobStatusUpdateMessage(
        job_id="job_123",
        status=JobStatus.RUNNING.value,
        previous_status=JobStatus.PENDING.value,
        trigger="start_processing",
    )

    result = await message_handlers._handle_status_update_async(message)

    assert result["status"] == "ignored"
    assert result["retryable"] is False
    assert result["reason"] == "invalid_transition"
    transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_status_update_treats_duplicate_status_as_success(monkeypatch):
    monkeypatch.setattr(message_handlers, "get_db_context", _fake_db_context)

    get_current_state = AsyncMock(return_value=JobStatus.RUNNING.value)
    transition = AsyncMock()
    monkeypatch.setattr(message_handlers._state_machine, "get_current_state", get_current_state)
    monkeypatch.setattr(message_handlers._state_machine, "transition", transition)

    message = JobStatusUpdateMessage(
        job_id="job_123",
        status=JobStatus.RUNNING.value,
        previous_status=JobStatus.PENDING.value,
        trigger="start_processing",
    )

    result = await message_handlers._handle_status_update_async(message)

    assert result["status"] == "success"
    assert result["idempotent"] is True
    transition.assert_not_awaited()
