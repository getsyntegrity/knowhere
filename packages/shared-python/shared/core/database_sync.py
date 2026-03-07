"""
Sync database engine for Celery worker (gevent pool).
Uses psycopg2 + psycogreen for cooperative DB access under gevent.
API service continues using the async engine in database.py.
"""
from contextlib import contextmanager
from typing import Generator

from loguru import logger
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from shared.core.config import settings

# Build sync database URL: replace asyncpg with psycopg2
_sync_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
)

sync_engine = create_engine(
    _sync_url,
    pool_size=settings.DB_SYNC_POOL_SIZE,
    max_overflow=settings.DB_SYNC_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    connect_args=settings.get_ssl_connect_args(),
)

logger.info(
    f"Sync database engine created "
    f"(pool_size={settings.DB_SYNC_POOL_SIZE}, max_overflow={settings.DB_SYNC_MAX_OVERFLOW})"
)

SyncSessionFactory = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
)


@event.listens_for(sync_engine, "connect")
def _on_connect(dbapi_connection, connection_record):
    logger.debug("New sync database connection established")


@event.listens_for(sync_engine, "invalidate")
def _on_invalidate(dbapi_connection, connection_record, exception):
    logger.warning(f"Sync database connection invalidated: {exception}")


@contextmanager
def get_sync_db_context() -> Generator[Session, None, None]:
    """Sync database session context manager for worker tasks."""
    session = SyncSessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        logger.warning("Sync database session rollback due to exception")
        session.rollback()
        raise
    finally:
        session.close()
