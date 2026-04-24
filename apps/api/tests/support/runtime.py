from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import psycopg2
import redis.asyncio as redis_asyncio
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

CONTRACT_DATABASE_NAME: str = "Knowhere_contract_test"
CONTRACT_REDIS_DATABASE: int = 14
CONTRACT_REDIS_HOST: str = "127.0.0.1"
CONTRACT_REDIS_PORT: int = 6379

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_API_ROOT: Path = _REPO_ROOT / "apps" / "api"
_SHARED_ROOT: Path = _REPO_ROOT / "packages" / "shared-python"
_TEST_TMP_ROOT: Path = Path("/tmp/knowhere-api-tests")
_STATIC_TABLES_TO_PRESERVE: frozenset[str] = frozenset(
    {
        "alembic_version",
        "tier_limits",
        "system_limits",
    }
)
_MODULE_NAMES_TO_CLEAR: tuple[str, ...] = (
    "main",
    "custom_openapi",
    "shared.core.config",
    "shared.core.config.app",
    "shared.core.config.base",
    "shared.core.config.database",
    "shared.core.config.redis",
    "shared.core.database",
    "scripts.local_dev_bootstrap_service",
)
_contract_storage_prepared: bool = False


def _ensure_import_paths() -> None:
    api_root_value: str = str(_API_ROOT)
    shared_root_value: str = str(_SHARED_ROOT)

    if api_root_value not in sys.path:
        sys.path.insert(0, api_root_value)

    if shared_root_value not in sys.path:
        sys.path.insert(0, shared_root_value)


def _ensure_test_directories() -> None:
    users_data_path: Path = _TEST_TMP_ROOT / "users"
    chromedriver_path: Path = _TEST_TMP_ROOT / "chromedriver"

    _TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    users_data_path.mkdir(parents=True, exist_ok=True)
    chromedriver_path.touch(exist_ok=True)


def _resolve_base_database_url() -> URL:
    configured_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://root:root123@127.0.0.1:5432/Knowhere",
    )
    return make_url(configured_url)


def get_contract_database_url() -> str:
    contract_database_url: URL = _resolve_base_database_url().set(
        database=CONTRACT_DATABASE_NAME
    )
    return contract_database_url.render_as_string(hide_password=False)


def _get_contract_sync_database_url() -> str:
    sync_database_url: URL = make_url(get_contract_database_url()).set(
        drivername="postgresql"
    )
    return sync_database_url.render_as_string(hide_password=False)


def _get_admin_sync_database_url() -> str:
    admin_database_url: URL = make_url(_get_contract_sync_database_url()).set(
        database="postgres"
    )
    return admin_database_url.render_as_string(hide_password=False)


def configure_contract_environment(monkeypatch: MonkeyPatch) -> None:
    _ensure_test_directories()

    environment: dict[str, str] = {
        "ENVIRONMENT": "development",
        "DEBUG": "true",
        "SECRET_KEY": "test-secret-key",
        "DATABASE_URL": get_contract_database_url(),
        "DB_SSL_MODE": "disable",
        "REDIS_HOST": CONTRACT_REDIS_HOST,
        "REDIS_PORT": str(CONTRACT_REDIS_PORT),
        "REDIS_DATABASE": str(CONTRACT_REDIS_DATABASE),
        "CELERY_REDIS_URL": (
            f"redis://{CONTRACT_REDIS_HOST}:{CONTRACT_REDIS_PORT}/{CONTRACT_REDIS_DATABASE}"
        ),
        "TMP_PATH": str(_TEST_TMP_ROOT),
        "FONT_PATH": str(_TEST_TMP_ROOT),
        "CHROMEDRIVER_PATH": str(_TEST_TMP_ROOT / "chromedriver"),
        "USERS_DATA_PATH": str(_TEST_TMP_ROOT / "users"),
        "S3_BUCKET_NAME": "knowhere-test-bucket",
        "S3_ACCESS_KEY_ID": "test-access-key",
        "S3_SECRET_ACCESS_KEY": "test-secret-key",
        "S3_TEMP_PATH": str(_TEST_TMP_ROOT),
        "S3_ENDPOINT_URL": "http://127.0.0.1:4566",
        "S3_PRIVATE_DOMAIN": "http://127.0.0.1:4566",
        "S3_UPLOADS_BUCKET": "knowhere-test-uploads",
        "S3_RESULTS_BUCKET": "knowhere-test-results",
        "S3_REGION": "us-west-1",
        "S3_USE_SSL": "false",
        "S3_ADDRESSING_STYLE": "path",
        "DS_KEY": "test-deepseek-key",
        "DS_URL": "https://example.com/v1",
        "QSTASH_CALLBACK_BASE_URL": "http://localhost:5005/api/v1",
    }

    for key, value in environment.items():
        monkeypatch.setenv(key, value)


def clear_application_modules() -> None:
    cached_module_names: list[str] = list(sys.modules)

    for module_name in cached_module_names:
        if module_name in _MODULE_NAMES_TO_CLEAR:
            sys.modules.pop(module_name, None)
            continue

        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)


def _ensure_contract_database_exists() -> None:
    contract_database_name: str = make_url(get_contract_database_url()).database or ""

    connection = psycopg2.connect(_get_admin_sync_database_url())
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (contract_database_name,),
            )
            database_exists: bool = cursor.fetchone() is not None

            if not database_exists:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(contract_database_name)
                    )
                )
    finally:
        connection.close()


def _initialize_contract_database() -> None:
    contract_database_name: str = make_url(get_contract_database_url()).database or ""

    admin_connection = psycopg2.connect(_get_admin_sync_database_url())
    admin_connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with admin_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER DATABASE {} SET search_path TO public").format(
                    sql.Identifier(contract_database_name)
                )
            )
    finally:
        admin_connection.close()

    contract_connection = psycopg2.connect(_get_contract_sync_database_url())
    contract_connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with contract_connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
            cursor.execute("SET timezone = 'UTC'")
    finally:
        contract_connection.close()


async def _ensure_contract_user_table() -> None:
    _ensure_import_paths()
    clear_application_modules()

    bootstrap_module: ModuleType = importlib.import_module(
        "scripts.local_dev_bootstrap_service"
    )
    bootstrap_service = bootstrap_module.LocalDevelopmentBootstrapService()
    await bootstrap_service.ensure_user_table_exists()


def _run_contract_migrations() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "heads"],
        cwd=str(_API_ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Contract database migration failed: "
            f"{result.stderr or result.stdout or 'unknown error'}"
        )


async def _create_contract_engine() -> AsyncEngine:
    return create_async_engine(get_contract_database_url(), future=True)


async def prepare_contract_storage() -> None:
    global _contract_storage_prepared

    _ensure_import_paths()

    if not _contract_storage_prepared:
        _ensure_contract_database_exists()
        _initialize_contract_database()
        await _ensure_contract_user_table()
        _run_contract_migrations()
        _contract_storage_prepared = True

    await reset_contract_database()
    await reset_contract_redis()


async def seed_contract_developer() -> dict[str, str | int]:
    _ensure_import_paths()

    bootstrap_module: ModuleType = importlib.import_module(
        "scripts.local_dev_bootstrap_service"
    )
    bootstrap_service = bootstrap_module.LocalDevelopmentBootstrapService()
    engine: AsyncEngine = await _create_contract_engine()
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            await bootstrap_service.seed_local_developer(session)
            await session.commit()
    finally:
        await engine.dispose()

    return bootstrap_module.LocalDevelopmentBootstrapService.get_local_developer_profile()


async def reset_contract_database() -> None:
    engine: AsyncEngine = await _create_contract_engine()

    try:
        async with engine.begin() as connection:
            table_names_result = await connection.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                    """
                )
            )
            table_names: list[str] = [
                row[0]
                for row in table_names_result.fetchall()
                if row[0] not in _STATIC_TABLES_TO_PRESERVE
            ]

            if table_names:
                qualified_table_list: str = ", ".join(
                    f'public."{table_name}"' for table_name in table_names
                )
                await connection.execute(
                    text(
                        f"TRUNCATE TABLE {qualified_table_list} RESTART IDENTITY CASCADE"
                    )
                )
    finally:
        await engine.dispose()


async def reset_contract_redis() -> None:
    redis_client = redis_asyncio.Redis(
        host=CONTRACT_REDIS_HOST,
        port=CONTRACT_REDIS_PORT,
        db=CONTRACT_REDIS_DATABASE,
        decode_responses=True,
    )

    try:
        await redis_client.flushdb()
    finally:
        await redis_client.aclose()
