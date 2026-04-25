from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pytest import MonkeyPatch
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url

from tests.support.runtime import clear_application_modules, configure_contract_environment

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_API_ROOT: Path = _REPO_ROOT / "apps" / "api"
_ALEMBIC_ROOT: Path = _API_ROOT / "alembic"
_ALEMBIC_INI_PATH: Path = _API_ROOT / "alembic.ini"


def _resolve_base_database_url() -> URL:
    configured_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://root:root123@127.0.0.1:5432/Knowhere",
    )
    return make_url(configured_url)


def _build_database_urls(database_name: str) -> tuple[str, str]:
    async_database_url = _resolve_base_database_url().set(
        database=database_name
    ).render_as_string(hide_password=False)
    sync_database_url = make_url(async_database_url).set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)
    return async_database_url, sync_database_url


def _build_admin_database_url(sync_database_url: str) -> str:
    return make_url(sync_database_url).set(database="postgres").render_as_string(
        hide_password=False
    )


def _create_database(*, database_name: str, admin_database_url: str) -> None:
    connection = psycopg2.connect(admin_database_url)
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
            )
    finally:
        connection.close()


def _drop_database(*, database_name: str, admin_database_url: str) -> None:
    connection = psycopg2.connect(admin_database_url)
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid()
                """,
                (database_name,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(database_name)
                )
            )
    finally:
        connection.close()


def _initialize_database(sync_database_url: str) -> None:
    connection = psycopg2.connect(sync_database_url)
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "user" (
                    id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE
                )
                """
            )
    finally:
        connection.close()


def _clear_model_modules() -> None:
    cached_module_names = list(sys.modules)
    for module_name in cached_module_names:
        if module_name == "shared.models" or module_name.startswith("shared.models."):
            sys.modules.pop(module_name, None)


@pytest.fixture
def alembic_config() -> dict[str, str]:
    return {
        "file": str(_ALEMBIC_INI_PATH),
        "script_location": str(_ALEMBIC_ROOT),
    }


@pytest.fixture
def alembic_engine(monkeypatch: MonkeyPatch) -> Iterator[Engine]:
    configure_contract_environment(monkeypatch)

    database_name = f"knowhere_migration_{uuid4().hex[:12]}"
    async_database_url, sync_database_url = _build_database_urls(database_name)
    admin_database_url = _build_admin_database_url(sync_database_url)

    monkeypatch.setenv("DATABASE_URL", async_database_url)
    monkeypatch.setenv("DB_SSL_MODE", "disable")
    clear_application_modules()
    _clear_model_modules()

    _create_database(
        database_name=database_name,
        admin_database_url=admin_database_url,
    )
    _initialize_database(sync_database_url)

    engine = create_engine(sync_database_url, future=True)

    try:
        yield engine
    finally:
        engine.dispose()
        clear_application_modules()
        _clear_model_modules()
        _drop_database(
            database_name=database_name,
            admin_database_url=admin_database_url,
        )
