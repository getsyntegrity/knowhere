import importlib
import os
import sys
from typing import Any

import sqlalchemy

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("USERS_DATA_PATH", "/tmp")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")


def _reload_database_sync_module() -> Any:
    sys.modules.pop("shared.core.database_sync", None)
    return importlib.import_module("shared.core.database_sync")


def test_database_sync_import_does_not_create_engine(monkeypatch) -> None:
    create_engine_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake_create_engine(*args: Any, **kwargs: Any) -> object:
        create_engine_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", fake_create_engine)

    module = _reload_database_sync_module()

    assert create_engine_calls == []
    assert module._sync_engine is None


def test_get_sync_engine_creates_singleton_once(monkeypatch) -> None:
    fake_engine = object()
    create_engine_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    event_listen_calls: list[str] = []

    def fake_create_engine(*args: Any, **kwargs: Any) -> object:
        create_engine_calls.append((args, kwargs))
        return fake_engine

    def fake_event_listen(target: object, identifier: str, fn: Any) -> None:
        assert target is fake_engine
        event_listen_calls.append(identifier)

    monkeypatch.setattr(sqlalchemy, "create_engine", fake_create_engine)
    monkeypatch.setattr(sqlalchemy.event, "listen", fake_event_listen)

    module = _reload_database_sync_module()

    engine_one = module.get_sync_engine()
    engine_two = module.get_sync_engine()

    assert engine_one is fake_engine
    assert engine_two is fake_engine
    assert len(create_engine_calls) == 1
    assert event_listen_calls == ["connect", "invalidate"]
