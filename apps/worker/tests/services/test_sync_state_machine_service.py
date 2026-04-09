from types import SimpleNamespace
from unittest.mock import MagicMock

from shared.core.state_machine.service_sync import SyncStateMachineService
from shared.core.state_machine.states import JobStatus


def test_cas_update_state_uses_naive_utc_timestamp():
    service = SyncStateMachineService(redis_service=MagicMock())
    db = MagicMock()
    db.execute.return_value = SimpleNamespace(rowcount=1)

    success = service._cas_update_state(db, "job_123", JobStatus.FAILED.value, 0)

    assert success is True
    statement = db.execute.call_args.args[0]
    updated_at = statement.compile().params["updated_at"]
    assert updated_at.tzinfo is None


def test_transition_does_not_retry_on_cas_database_error():
    service = SyncStateMachineService(redis_service=MagicMock())
    db = MagicMock()
    db.is_active = True

    service._get_job_with_version = MagicMock(
        return_value=SimpleNamespace(
            job_id="job_123",
            status=JobStatus.PENDING.value,
            version=0,
        )
    )
    service._record_audit_log = MagicMock()
    service._cas_update_state = MagicMock(side_effect=RuntimeError("db exploded"))
    service._update_redis_cache = MagicMock()

    success = service.transition(db, "job_123", JobStatus.RUNNING.value)

    assert success is False
    service._cas_update_state.assert_called_once()
    service._update_redis_cache.assert_not_called()
    db.rollback.assert_called_once()
