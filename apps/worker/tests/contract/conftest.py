from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from typing import Protocol

import pytest
from pytest_postgresql import factories
from pytest import MonkeyPatch

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_API_ROOT: Path = _REPO_ROOT / "apps" / "api"
_API_RUNTIME_PATH: Path = _REPO_ROOT / "apps" / "api" / "tests" / "support" / "runtime.py"
_API_ENVIRONMENT_PATH: Path = _API_ROOT / "scripts" / "ensure_test_environment.py"
_WORKER_ROOT: Path = _REPO_ROOT / "apps" / "worker"


class PostgreSQLProcess(Protocol):
    @property
    def host(self) -> str: ...

    @property
    def port(self) -> int: ...

    @property
    def user(self) -> str: ...

    @property
    def password(self) -> str | None: ...


def _load_module(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_name} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


_API_RUNTIME: ModuleType = _load_module("api_contract_runtime", _API_RUNTIME_PATH)
_API_ENVIRONMENT: ModuleType = _load_module(
    "api_test_environment",
    _API_ENVIRONMENT_PATH,
)


def _resolve_postgresql_executable() -> str | None:
    configured_executable: str | None = os.getenv("PYTEST_POSTGRESQL_EXECUTABLE")

    if configured_executable:
        return configured_executable

    executable_path = _API_ENVIRONMENT.find_executable("pg_ctl")
    return str(executable_path) if executable_path is not None else None


postgresql_proc = factories.postgresql_proc(
    executable=_resolve_postgresql_executable(),
    port=None,
)


@pytest.fixture
def worker_contract_environment(
    monkeypatch: MonkeyPatch,
    postgresql_proc: PostgreSQLProcess,
) -> Generator[None, None, None]:
    _API_RUNTIME.configure_contract_environment(monkeypatch, postgresql_proc)
    asyncio.run(_API_RUNTIME.prepare_contract_storage())

    worker_root_value = str(_WORKER_ROOT)
    if worker_root_value in sys.path:
        sys.path.remove(worker_root_value)
    sys.path.insert(0, worker_root_value)
    _API_RUNTIME.clear_application_modules()

    try:
        yield
    finally:
        _API_RUNTIME.cleanup_contract_runtime(remove_test_directories=True)
