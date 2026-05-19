from __future__ import annotations

import asyncio
import importlib
import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from pytest_postgresql import factories
from pytest import MonkeyPatch
from shared.testing import contract_runtime
from shared.testing.contract_runtime import PostgreSQLProcess
from shared.testing.postgresql_environment import find_executable

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_WORKER_ROOT: Path = _REPO_ROOT / "apps" / "worker"


def _resolve_postgresql_executable() -> str | None:
    configured_executable: str | None = os.getenv("PYTEST_POSTGRESQL_EXECUTABLE")

    if configured_executable:
        return configured_executable

    executable_path = find_executable("pg_ctl")
    return str(executable_path) if executable_path is not None else None


_contract_postgresql_proc = factories.postgresql_proc(
    executable=_resolve_postgresql_executable(),
    port=contract_runtime.CONTRACT_POSTGRESQL_PORT_RANGE,
)


@pytest.fixture(scope="session")
def postgresql_proc(
    _contract_postgresql_proc: PostgreSQLProcess,
) -> Generator[PostgreSQLProcess, None, None]:
    try:
        yield _contract_postgresql_proc
    finally:
        contract_runtime.cleanup_contract_runtime(remove_test_directories=True)
        contract_runtime.drop_contract_database(_contract_postgresql_proc)


@pytest.fixture
def worker_contract_environment(
    monkeypatch: MonkeyPatch,
    postgresql_proc: PostgreSQLProcess,
) -> Generator[None, None, None]:
    contract_runtime.configure_contract_environment(monkeypatch, postgresql_proc)
    asyncio.run(contract_runtime.prepare_contract_storage())

    worker_root_value = str(_WORKER_ROOT)
    if worker_root_value in sys.path:
        sys.path.remove(worker_root_value)
    sys.path.insert(0, worker_root_value)
    contract_runtime.clear_application_modules()

    from shared.core.celery_app import get_celery_app

    celery_app = get_celery_app()
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", False)
    importlib.import_module("app.core.tasks.document_ingestion_tasks")

    try:
        yield
    finally:
        contract_runtime.cleanup_contract_runtime(remove_test_directories=True)
