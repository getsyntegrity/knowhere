import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable, TypeVar

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from shared.core.config import settings
from shared.core.constants import ProcessingConstants

logger = logging.getLogger(__name__)

# Get SSL connection parameters.
ssl_connect_args = settings.get_async_ssl_connect_args()

engine = create_async_engine(
    settings.DATABASE_URL,
    # echo=True,  # Uncomment to print SQL statements for debugging.
    # Connection-pool configuration.
    pool_size=ProcessingConstants.DB_POOL_SIZE,
    max_overflow=ProcessingConstants.DB_MAX_OVERFLOW,
    pool_recycle=ProcessingConstants.DB_POOL_RECYCLE,
    pool_timeout=ProcessingConstants.DB_POOL_TIMEOUT,
    pool_pre_ping=ProcessingConstants.DB_POOL_PRE_PING,
    pool_reset_on_return=ProcessingConstants.DB_POOL_RESET_ON_RETURN,
    # PostgreSQL-specific configuration.
    connect_args={
        "server_settings": {
            "application_name": "knowhere_api",
            "timezone": "UTC",
            "statement_timeout": "30000",  # 30-second statement timeout.
            "idle_in_transaction_session_timeout": "60000",  # 60-second idle transaction timeout.
        },
        "command_timeout": 30,
        # Merge in SSL config.
        **ssl_connect_args,
    },
    # Connection-pool event hooks.
    pool_events=[],
)
# Create the async session factory.
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # Keep ORM objects usable after commit.
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session with the SQLAlchemy 2.0 async-with pattern.

    Uses AsyncSession as context manager for automatic cleanup.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Create an app-level context manager for operations without an injected DB session.
@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession | None = None
    try:
        session = AsyncSessionFactory()
        yield session
        try:
            await session.commit()
        except Exception as commit_error:
            # Roll back if commit fails.
            try:
                if session.is_active:
                    await session.rollback()
            except Exception as rollback_error:
                # Log rollback failures only to avoid cross-event-loop connection work.
                logger.warning(f"Database session rollback failed: {rollback_error}")
            raise commit_error
    except Exception:
        # Attempt rollback if the session exists and is still active.
        if session:
            try:
                if session.is_active:
                    await session.rollback()
            except Exception as rollback_error:
                # Log rollback failures only to avoid cross-event-loop connection work.
                logger.warning(
                    f"Database session rollback failed during exception handling: {rollback_error}"
                )
            raise
    finally:
        # Close the session safely.
        if session:
            try:
                await session.close()
            except Exception as close_error:
                # Log close failures only to avoid cross-event-loop connection work.
                logger.warning(f"Database session close failed: {close_error}")


# Helper for DB work when a session cannot be passed in directly.
T = TypeVar("T")


async def db_operation(operation: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """
    Execute a database operation via a managed session.
    """
    async with get_db_context() as db:
        return await operation(db)


Base = declarative_base()


async def create_tables():
    """Create all database tables."""
    async with engine.begin() as conn:
        # Import all models to ensure they are registered.
        pass

        # Create all tables.
        await conn.run_sync(Base.metadata.create_all)


# Connection-pool monitoring and health checks.
class DatabaseHealthChecker:
    """Database health checker."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.last_check: datetime | None = None
        self.is_healthy = False

    def _pool_metric(self, name: str) -> int:
        metric = getattr(self.engine.pool, name, None)
        if callable(metric):
            value = metric()
            return int(value) if isinstance(value, (int, float)) else 0
        return 0

    async def check_health(self) -> dict[str, object]:
        """Check database connection health."""
        try:
            start_time = time.time()
            async with self.engine.begin() as conn:
                # Run a simple query to validate connectivity.
                result = await conn.execute(text("SELECT 1 as health_check"))
                row = result.fetchone()

                if row and row[0] == 1:
                    self.is_healthy = True
                    self.last_check = datetime.now()

                    # Collect current connection-pool status.
                    pool_status = self.get_pool_status()

                    return {
                        "status": "healthy",
                        "response_time_ms": round((time.time() - start_time) * 1000, 2),
                        "last_check": self.last_check.isoformat(),
                        "pool_status": pool_status,
                    }
                else:
                    self.is_healthy = False
                    return {
                        "status": "unhealthy",
                        "error": "Health check query failed",
                        "last_check": (
                            self.last_check.isoformat() if self.last_check else None
                        ),
                    }
        except Exception as e:
            self.is_healthy = False
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": self.last_check.isoformat() if self.last_check else None,
            }

    def get_pool_status(self) -> dict[str, int]:
        """Return connection-pool status details."""
        status = {
            "size": self._pool_metric("size"),
            "checked_in": self._pool_metric("checkedin"),
            "checked_out": self._pool_metric("checkedout"),
            "overflow": self._pool_metric("overflow"),
        }
        status["invalid"] = self._pool_metric("invalid")
        return status

    async def get_database_info(self) -> dict[str, object]:
        """Return database metadata and connection status."""
        try:
            async with self.engine.begin() as conn:
                # Read the database version.
                version_result = await conn.execute(text("SELECT version()"))
                version_row = version_result.fetchone()
                if version_row is None:
                    return {"error": "Failed to read database version"}
                version = version_row[0]

                # Read the current active-connection count.
                connections_result = await conn.execute(
                    text("""
                    SELECT count(*) as active_connections 
                    FROM pg_stat_activity 
                    WHERE state = 'active'
                """)
                )
                active_connections_row = connections_result.fetchone()
                if active_connections_row is None:
                    return {"error": "Failed to read active connection count"}
                active_connections = active_connections_row[0]

                # Read the current database size.
                size_result = await conn.execute(
                    text("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
                """)
                )
                db_size_row = size_result.fetchone()
                if db_size_row is None:
                    return {"error": "Failed to read database size"}
                db_size = db_size_row[0]

                return {
                    "version": version,
                    "active_connections": active_connections,
                    "database_size": db_size,
                    "pool_status": self.get_pool_status(),
                }
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {"error": str(e)}


# Shared health-checker instance.
db_health_checker = DatabaseHealthChecker(engine)


async def get_database_health() -> dict:
    """Return database health status."""
    return await db_health_checker.check_health()


async def get_database_info() -> dict:
    """Return database information."""
    return await db_health_checker.get_database_info()


# Database retry helpers.
class DatabaseRetryManager:
    """Database retry manager."""

    def __init__(
        self, max_retries: int = 3, retry_delay: float = 1.0, backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor

    async def execute_with_retry(
        self,
        operation: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Execute a database operation with retries."""
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Database operation failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                if attempt < self.max_retries:
                    delay = self.retry_delay * (self.backoff_factor**attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error("All retry attempts failed for database operation")
                    raise last_exception

        raise RuntimeError("Database retry manager exhausted without raising") from (
            last_exception
        )


# Shared retry-manager instance.
db_retry_manager = DatabaseRetryManager()


async def safe_db_operation(
    operation: Callable[..., Awaitable[T]], *args: object, **kwargs: object
) -> T:
    """Run a database operation through the retry manager."""
    return await db_retry_manager.execute_with_retry(operation, *args, **kwargs)


# Connection-pool event listeners.
def setup_pool_event_listeners():
    """Register connection-pool event listeners."""

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_connection, connection_record):
        """Handle new connection events."""
        logger.info("New database connection established")

    @event.listens_for(engine.sync_engine, "checkout")
    def on_checkout(dbapi_connection, connection_record, connection_proxy):
        """Handle connection checkout events."""
        logger.debug("Connection checked out from pool")

    @event.listens_for(engine.sync_engine, "checkin")
    def on_checkin(dbapi_connection, connection_record):
        """Handle connection check-in events."""
        logger.debug("Connection checked in to pool")

    @event.listens_for(engine.sync_engine, "invalidate")
    def on_invalidate(dbapi_connection, connection_record, exception):
        """Handle connection invalidation events."""
        logger.warning(f"Database connection invalidated: {exception}")

setup_pool_event_listeners()


# Connection-pool prewarming.
async def prewarm_connection_pool():
    """Prewarm the connection pool by opening connections early."""
    if not ProcessingConstants.DB_POOL_PREWARM:
        return

    logger.info("Starting connection pool prewarming...")
    try:
        # Warm the base connection pool.
        connections_to_warm = min(ProcessingConstants.DB_POOL_SIZE, 5)
        tasks = []

        for _ in range(connections_to_warm):
            task = asyncio.create_task(_warm_connection())
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(
            f"Connection pool prewarming completed. Warmed {connections_to_warm} connections."
        )

    except Exception as e:
        logger.warning(f"Connection pool prewarming failed: {e}")


async def _warm_connection():
    """Warm a single connection."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text(ProcessingConstants.DB_VALIDATION_QUERY))
    except Exception as e:
        logger.debug(f"Connection warming failed: {e}")


# Database performance monitoring.
class DatabasePerformanceMonitor:
    """Database performance monitor."""

    def __init__(self):
        self.query_times = []
        self.connection_usage = []
        self.error_count = 0

    def record_query_time(self, query_time_ms: float):
        """Record query latency."""
        self.query_times.append(query_time_ms)
        # Keep only the most recent 1000 query samples.
        if len(self.query_times) > 1000:
            self.query_times = self.query_times[-1000:]

    def record_connection_usage(self, pool_status: dict):
        """Record connection-pool usage."""
        self.connection_usage.append(
            {
                "timestamp": datetime.now().isoformat(),
                "checked_out": pool_status.get("checked_out", 0),
                "checked_in": pool_status.get("checked_in", 0),
                "overflow": pool_status.get("overflow", 0),
            }
        )
        # Keep only the most recent 100 samples.
        if len(self.connection_usage) > 100:
            self.connection_usage = self.connection_usage[-100:]

    def record_error(self):
        """Record an error occurrence."""
        self.error_count += 1

    def get_performance_stats(self) -> dict:
        """Return collected performance statistics."""
        if not self.query_times:
            return {"error": "No query data available"}

        return {
            "query_stats": {
                "count": len(self.query_times),
                "avg_time_ms": round(sum(self.query_times) / len(self.query_times), 2),
                "min_time_ms": round(min(self.query_times), 2),
                "max_time_ms": round(max(self.query_times), 2),
                "p95_time_ms": round(
                    sorted(self.query_times)[int(len(self.query_times) * 0.95)], 2
                ),
            },
            "connection_stats": {
                "recent_usage": (
                    self.connection_usage[-10:] if self.connection_usage else []
                ),
                "total_errors": self.error_count,
            },
        }


# Shared performance-monitor instance.
db_performance_monitor = DatabasePerformanceMonitor()


async def get_database_performance() -> dict:
    """Return database performance statistics."""
    return db_performance_monitor.get_performance_stats()


async def safe_dispose_engine(db_engine):
    """
    Close a database engine safely.

    Args:
        db_engine: SQLAlchemy async engine instance.
    """
    try:
        if db_engine:
            # dispose() is synchronous, so run it in a worker thread.
            await asyncio.to_thread(db_engine.dispose)
            logger.info("Database engine shut down safely")
    except Exception as e:
        logger.error(f"Error while shutting down the database engine: {e}")
        # Suppress dispose failures to avoid blocking app shutdown.
