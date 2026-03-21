from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.core.state_machine.service import AsyncStateMachineService
from shared.core.state_machine.states import JobStatus


@pytest.mark.asyncio
async def test_cas_update_state_uses_naive_utc_timestamp():
    service = AsyncStateMachineService(redis_service=AsyncMock())
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))

    success = await service._cas_update_state(db, "job_123", JobStatus.FAILED.value, 0)

    assert success is True
    statement = db.execute.await_args.args[0]
    updated_at = statement.compile().params["updated_at"]
    assert updated_at.tzinfo is None


@pytest.mark.asyncio
async def test_transition_does_not_retry_on_cas_database_error():
    service = AsyncStateMachineService(redis_service=AsyncMock())
    db = AsyncMock()
    db.is_active = True

    service._get_job_with_version = AsyncMock(
        return_value=SimpleNamespace(
            job_id="job_123",
            status=JobStatus.PENDING.value,
            version=0,
        )
    )
    service._record_audit_log = AsyncMock()
    service._cas_update_state = AsyncMock(side_effect=RuntimeError("db exploded"))
    service._update_redis_cache = AsyncMock()

    success = await service.transition(db, "job_123", JobStatus.RUNNING.value)

    assert success is False
    assert service._cas_update_state.await_count == 1
    service._update_redis_cache.assert_not_awaited()
    db.rollback.assert_awaited_once()
