from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_API_RUNTIME_PATH: Path = _REPO_ROOT / "apps" / "api" / "tests" / "support" / "runtime.py"
_WORKER_ROOT: Path = _REPO_ROOT / "apps" / "worker"


def _load_api_contract_runtime() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "api_contract_runtime",
        _API_RUNTIME_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load API contract runtime from {_API_RUNTIME_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_API_RUNTIME: ModuleType = _load_api_contract_runtime()


@pytest.fixture
def worker_contract_environment(monkeypatch: MonkeyPatch) -> Generator[None, None, None]:
    _API_RUNTIME.configure_contract_environment(monkeypatch)
    asyncio.run(_API_RUNTIME.prepare_contract_storage())
    worker_root_value = str(_WORKER_ROOT)
    if worker_root_value in sys.path:
        sys.path.remove(worker_root_value)
    sys.path.insert(0, worker_root_value)
    _API_RUNTIME.clear_application_modules()

    try:
        yield
    finally:
        _API_RUNTIME.clear_application_modules()


def _insert_user(connection: Connection, *, user_id: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO "user" (id, name, email)
            VALUES (:user_id, :name, :email)
            """
        ),
        {
            "user_id": user_id,
            "name": f"Worker Contract User {user_id}",
            "email": f"{user_id}@worker-contract.knowhere.local",
        },
    )


def _insert_job(
    connection: Connection,
    *,
    job_id: str,
    user_id: str,
    status: str,
    updated_at: datetime,
) -> None:
    created_at = updated_at - timedelta(minutes=5)
    job_metadata = json.dumps(
        {
            "document_id": f"doc_{uuid4().hex[:12]}",
            "namespace": "worker-contract",
            "source_type": "file",
        }
    )

    connection.execute(
        text(
            """
            INSERT INTO jobs (
                job_id,
                user_id,
                job_type,
                status,
                source_type,
                webhook_enabled,
                job_metadata,
                version,
                created_at,
                updated_at,
                credits_charged,
                billing_status
            ) VALUES (
                :job_id,
                :user_id,
                :job_type,
                :status,
                :source_type,
                :webhook_enabled,
                CAST(:job_metadata AS JSON),
                :version,
                :created_at,
                :updated_at,
                :credits_charged,
                :billing_status
            )
            """
        ),
        {
            "job_id": job_id,
            "user_id": user_id,
            "job_type": "kb_management",
            "status": status,
            "source_type": "file",
            "webhook_enabled": False,
            "job_metadata": job_metadata,
            "version": 0,
            "created_at": created_at,
            "updated_at": updated_at,
            "credits_charged": 0,
            "billing_status": "pending",
        },
    )


def _load_worker_modules() -> tuple[Any, Engine]:
    import app.core.tasks.stale_job_sweeper as stale_job_sweeper
    from shared.core.database_sync import get_sync_engine

    return stale_job_sweeper, get_sync_engine()


def test_should_expire_stale_jobs_and_persist_failure_state(
    worker_contract_environment: None,
) -> None:
    stale_job_id = f"job_stale_{uuid4().hex[:12]}"
    fresh_job_id = f"job_fresh_{uuid4().hex[:12]}"
    user_id = f"worker-user-{uuid4().hex[:12]}"

    stale_job_sweeper, engine = _load_worker_modules()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with engine.begin() as connection:
        _insert_user(connection, user_id=user_id)
        _insert_job(
            connection,
            job_id=stale_job_id,
            user_id=user_id,
            status="running",
            updated_at=now - timedelta(days=1),
        )
        _insert_job(
            connection,
            job_id=fresh_job_id,
            user_id=user_id,
            status="waiting-file",
            updated_at=now,
        )

    result = stale_job_sweeper.expire_stale_jobs()

    assert result == {"status": "success", "expired": 1, "skipped": 0}

    with engine.begin() as connection:
        stale_job_row = (
            connection.execute(
                text(
                    """
                    SELECT status, error_code, error_message
                    FROM jobs
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": stale_job_id},
            )
            .mappings()
            .one()
        )
        fresh_job_row = (
            connection.execute(
                text(
                    """
                    SELECT status
                    FROM jobs
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": fresh_job_id},
            )
            .mappings()
            .one()
        )
        audit_log_row = (
            connection.execute(
                text(
                    """
                    SELECT from_state, to_state, transition_reason, transition_metadata
                    FROM job_state_audit_logs
                    WHERE job_id = :job_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"job_id": stale_job_id},
            )
            .mappings()
            .one()
        )

    audit_metadata = dict(audit_log_row["transition_metadata"])

    assert stale_job_row["status"] == "failed"
    assert stale_job_row["error_code"] == stale_job_sweeper.JOB_EXPIRED_ERROR_CODE
    assert stale_job_row["error_message"] == stale_job_sweeper.JOB_EXPIRED_ERROR_MESSAGE
    assert fresh_job_row["status"] == "waiting-file"
    assert audit_log_row["from_state"] == "running"
    assert audit_log_row["to_state"] == "failed"
    assert audit_log_row["transition_reason"] == "mark_failed"
    assert audit_metadata["sweeper"] is True
    assert audit_metadata["stale_status"] == "running"
    assert audit_metadata["error_code"] == stale_job_sweeper.JOB_EXPIRED_ERROR_CODE


def test_should_skip_duplicate_beat_firing_with_the_real_periodic_redis_lock(
    worker_contract_environment: None,
) -> None:
    stale_job_sweeper, _ = _load_worker_modules()

    first_result = stale_job_sweeper.expire_stale_jobs()
    second_result = stale_job_sweeper.expire_stale_jobs()

    assert first_result == {"status": "success", "expired": 0, "skipped": 0}
    assert second_result == {
        "status": "skipped",
        "reason": "duplicate Beat firing",
    }
