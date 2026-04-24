from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.common import job_start_service
from shared.core.exceptions.domain_exceptions import UnavailableException
from shared.core.state_machine.states import JobStatus


@contextmanager
def _fake_db_context(job_status: str):
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        job_id="job_123", status=job_status
    )

    db = MagicMock()
    db.execute.return_value = result
    yield db


def test_mark_job_running_transitions_pending_job(monkeypatch):
    monkeypatch.setattr(
        job_start_service,
        "get_sync_db_context",
        lambda: _fake_db_context(JobStatus.PENDING.value),
    )

    state_machine = MagicMock()
    state_machine.transition.return_value = True
    state_machine_cls = MagicMock(return_value=state_machine)
    monkeypatch.setattr(job_start_service, "SyncStateMachineService", state_machine_cls)

    job_start_service.mark_job_running("job_123", redis_service=MagicMock())

    state_machine.transition.assert_called_once()


def test_mark_job_running_retries_when_job_still_waiting_for_file(monkeypatch):
    monkeypatch.setattr(
        job_start_service,
        "get_sync_db_context",
        lambda: _fake_db_context(JobStatus.WAITING_FILE.value),
    )

    state_machine = MagicMock()
    state_machine_cls = MagicMock(return_value=state_machine)
    monkeypatch.setattr(job_start_service, "SyncStateMachineService", state_machine_cls)

    with pytest.raises(UnavailableException):
        job_start_service.mark_job_running("job_123", redis_service=MagicMock())

    state_machine.transition.assert_not_called()


def test_mark_job_running_is_idempotent_for_running_job(monkeypatch):
    monkeypatch.setattr(
        job_start_service,
        "get_sync_db_context",
        lambda: _fake_db_context(JobStatus.RUNNING.value),
    )

    state_machine = MagicMock()
    state_machine_cls = MagicMock(return_value=state_machine)
    monkeypatch.setattr(job_start_service, "SyncStateMachineService", state_machine_cls)

    job_start_service.mark_job_running("job_123", redis_service=MagicMock())

    state_machine.transition.assert_not_called()


@pytest.mark.parametrize(
    "terminal_state", [JobStatus.FAILED.value, JobStatus.DONE.value]
)
def test_mark_job_running_skips_terminal_job(monkeypatch, terminal_state):
    monkeypatch.setattr(
        job_start_service,
        "get_sync_db_context",
        lambda: _fake_db_context(terminal_state),
    )

    state_machine = MagicMock()
    state_machine_cls = MagicMock(return_value=state_machine)
    monkeypatch.setattr(job_start_service, "SyncStateMachineService", state_machine_cls)

    should_process = job_start_service.mark_job_running(
        "job_123", redis_service=MagicMock()
    )

    assert should_process is False
    state_machine.transition.assert_not_called()
