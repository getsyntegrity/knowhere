from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Generator
from pathlib import Path
from types import ModuleType

import pytest
from pytest import MonkeyPatch

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
