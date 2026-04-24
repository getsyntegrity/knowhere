import importlib
import sys
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from types import ModuleType

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from tests.support.runtime import (
    clear_application_modules,
    configure_contract_environment,
    prepare_contract_storage,
)

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_API_ROOT: Path = _REPO_ROOT / "apps" / "api"
_SHARED_ROOT: Path = _REPO_ROOT / "packages" / "shared-python"


def _ensure_import_paths() -> None:
    api_root_value: str = str(_API_ROOT)
    shared_root_value: str = str(_SHARED_ROOT)

    if api_root_value not in sys.path:
        sys.path.insert(0, api_root_value)

    if shared_root_value not in sys.path:
        sys.path.insert(0, shared_root_value)


async def _load_api_module(monkeypatch: MonkeyPatch) -> ModuleType:
    configure_contract_environment(monkeypatch)
    await prepare_contract_storage()
    _ensure_import_paths()
    clear_application_modules()
    return importlib.import_module("main")


@asynccontextmanager
async def _create_api_client(
    monkeypatch: MonkeyPatch,
) -> AsyncGenerator[AsyncClient, None]:
    api_module: ModuleType = await _load_api_module(monkeypatch)
    app = api_module.app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def api_client_factory(
    monkeypatch: MonkeyPatch,
) -> Callable[[], AbstractAsyncContextManager[AsyncClient]]:
    def create_api_client() -> AbstractAsyncContextManager[AsyncClient]:
        return _create_api_client(monkeypatch)

    return create_api_client
