import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Awaitable, Callable, TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from shared.core.config import settings

logger = logging.getLogger(__name__)

# 创建 SQLAlchemy 异步引擎
from shared.core.constants import ProcessingConstants

# 获取SSL连接参数
ssl_connect_args = settings.get_async_ssl_connect_args()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True, # 取消注释以在控制台打印 SQL 语句，用于调试
    # 连接池配置
    pool_size=ProcessingConstants.DB_POOL_SIZE,
    max_overflow=ProcessingConstants.DB_MAX_OVERFLOW,
    pool_recycle=ProcessingConstants.DB_POOL_RECYCLE,
    pool_timeout=ProcessingConstants.DB_POOL_TIMEOUT,
    pool_pre_ping=ProcessingConstants.DB_POOL_PRE_PING,
    pool_reset_on_return=ProcessingConstants.DB_POOL_RESET_ON_RETURN,
    # PostgreSQL 特定配置
    connect_args={
        "server_settings": {
            "application_name": "knowhere_api",
            "timezone": "UTC",
            "statement_timeout": "30000",  # 30秒查询超时
            "idle_in_transaction_session_timeout": "60000",  # 60秒空闲事务超时
        },
        "command_timeout": 30,
        # 合并SSL配置
        **ssl_connect_args,
    },
    # 连接池事件监听
    pool_events=[],
)
# 创建异步会话工厂
AsyncSessionFactory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # 防止在提交后 ORM 对象过期
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话，包含完善的错误处理"""
    session = None
    try:
        session = AsyncSessionFactory()
        yield session
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        if session:
            await session.close()
# 创建一个App上下文管理器，用于在无法传入db参数时执行数据库操作
@asynccontextmanager
async def get_db_context():
    session = None
    try:
        session = AsyncSessionFactory()
        yield session
        try:
            await session.commit()
        except Exception as commit_error:
            # 提交失败时回滚
            try:
                if session.is_active:
                    await session.rollback()
            except Exception as rollback_error:
                # 回滚失败时只记录日志，避免在不同事件循环中操作连接
                logger.warning(f"Database session rollback failed: {rollback_error}")
            raise commit_error
    except Exception as e:
        # 如果会话存在且活跃，尝试回滚
        if session:
            try:
                if session.is_active:
                    await session.rollback()
            except Exception as rollback_error:
                # 回滚失败时只记录日志，避免在不同事件循环中操作连接
                logger.warning(f"Database session rollback failed during exception handling: {rollback_error}")
            raise
    finally:
        # 安全地关闭会话
        if session:
            try:
                await session.close()
            except Exception as close_error:
                # 关闭失败时只记录日志，避免在不同事件循环中操作连接
                logger.warning(f"Database session close failed: {close_error}")
# 添加一个辅助函数，用于在无法传入db参数时执行数据库操作
T = TypeVar('T')
async def db_operation(operation: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """
    执行数据库操作的辅助函数
    用法示例:
    """
    async with get_db_context() as db:
        return await operation(db)
Base = declarative_base()

async def create_tables():
    """创建所有数据表"""
    async with engine.begin() as conn:
        # 导入所有模型以确保它们被注册
        pass

        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)

# 连接池监控和健康检查
class DatabaseHealthChecker:
    """数据库健康检查器"""
    
    def __init__(self, engine):
        self.engine = engine
        self.last_check = None
        self.is_healthy = False
    
    async def check_health(self) -> dict:
        """检查数据库连接健康状态"""
        try:
            start_time = time.time()
            async with self.engine.begin() as conn:
                # 执行简单查询测试连接
                result = await conn.execute(text("SELECT 1 as health_check"))
                row = result.fetchone()
                
                if row and row[0] == 1:
                    self.is_healthy = True
                    self.last_check = datetime.now()
                    
                    # 获取连接池状态
                    pool_status = self.get_pool_status()
                    
                    return {
                        "status": "healthy",
                        "response_time_ms": round((time.time() - start_time) * 1000, 2),
                        "last_check": self.last_check.isoformat(),
                        "pool_status": pool_status
                    }
                else:
                    self.is_healthy = False
                    return {
                        "status": "unhealthy",
                        "error": "Health check query failed",
                        "last_check": self.last_check.isoformat() if self.last_check else None
                    }
        except Exception as e:
            self.is_healthy = False
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": self.last_check.isoformat() if self.last_check else None
            }
    
    def get_pool_status(self) -> dict:
        """获取连接池状态信息"""
        pool = self.engine.pool
        status = {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
        # 检查是否有invalid方法（某些连接池类型可能没有）
        if hasattr(pool, 'invalid'):
            status["invalid"] = pool.invalid()
        else:
            status["invalid"] = 0
        return status
    
    async def get_database_info(self) -> dict:
        """获取数据库信息"""
        try:
            async with self.engine.begin() as conn:
                # 获取数据库版本
                version_result = await conn.execute(text("SELECT version()"))
                version = version_result.fetchone()[0]
                
                # 获取当前连接数
                connections_result = await conn.execute(text("""
                    SELECT count(*) as active_connections 
                    FROM pg_stat_activity 
                    WHERE state = 'active'
                """))
                active_connections = connections_result.fetchone()[0]
                
                # 获取数据库大小
                size_result = await conn.execute(text("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
                """))
                db_size = size_result.fetchone()[0]
                
                return {
                    "version": version,
                    "active_connections": active_connections,
                    "database_size": db_size,
                    "pool_status": self.get_pool_status()
                }
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {"error": str(e)}

# 创建健康检查器实例
db_health_checker = DatabaseHealthChecker(engine)

async def get_database_health() -> dict:
    """获取数据库健康状态"""
    return await db_health_checker.check_health()

async def get_database_info() -> dict:
    """获取数据库信息"""
    return await db_health_checker.get_database_info()

# 数据库连接重试机制
class DatabaseRetryManager:
    """数据库重试管理器"""
    
    def __init__(self, max_retries=3, retry_delay=1.0, backoff_factor=2.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
    
    async def execute_with_retry(self, operation, *args, **kwargs):
        """执行数据库操作，支持重试机制"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"Database operation failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                
                if attempt < self.max_retries:
                    delay = self.retry_delay * (self.backoff_factor ** attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All retry attempts failed for database operation")
                    raise last_exception
        
        raise last_exception

# 创建重试管理器实例
db_retry_manager = DatabaseRetryManager()

async def safe_db_operation(operation, *args, **kwargs):
    """安全的数据库操作，包含重试机制"""
    return await db_retry_manager.execute_with_retry(operation, *args, **kwargs)

# 连接池事件监听器
def setup_pool_event_listeners():
    """设置连接池事件监听器"""
    
    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_connection, connection_record):
        """连接建立时的回调"""
        logger.info("New database connection established")
    
    @event.listens_for(engine.sync_engine, "checkout")
    def on_checkout(dbapi_connection, connection_record, connection_proxy):
        """从连接池获取连接时的回调"""
        logger.debug("Connection checked out from pool")
    
    @event.listens_for(engine.sync_engine, "checkin")
    def on_checkin(dbapi_connection, connection_record):
        """连接归还到连接池时的回调"""
        logger.debug("Connection checked in to pool")
    
    @event.listens_for(engine.sync_engine, "invalidate")
    def on_invalidate(dbapi_connection, connection_record, exception):
        """连接失效时的回调"""
        logger.warning(f"Database connection invalidated: {exception}")

# 设置事件监听器
from sqlalchemy import event

setup_pool_event_listeners()

# 连接池预热功能
async def prewarm_connection_pool():
    """预热连接池，提前建立连接"""
    if not ProcessingConstants.DB_POOL_PREWARM:
        return
    
    logger.info("Starting connection pool prewarming...")
    try:
        # 预热基础连接池
        connections_to_warm = min(ProcessingConstants.DB_POOL_SIZE, 5)
        tasks = []
        
        for _ in range(connections_to_warm):
            task = asyncio.create_task(_warm_connection())
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Connection pool prewarming completed. Warmed {connections_to_warm} connections.")
        
    except Exception as e:
        logger.warning(f"Connection pool prewarming failed: {e}")

async def _warm_connection():
    """预热单个连接"""
    try:
        async with engine.begin() as conn:
            await conn.execute(text(ProcessingConstants.DB_VALIDATION_QUERY))
    except Exception as e:
        logger.debug(f"Connection warming failed: {e}")

# 数据库性能监控
class DatabasePerformanceMonitor:
    """数据库性能监控器"""
    
    def __init__(self):
        self.query_times = []
        self.connection_usage = []
        self.error_count = 0
    
    def record_query_time(self, query_time_ms: float):
        """记录查询时间"""
        self.query_times.append(query_time_ms)
        # 只保留最近1000次查询的记录
        if len(self.query_times) > 1000:
            self.query_times = self.query_times[-1000:]
    
    def record_connection_usage(self, pool_status: dict):
        """记录连接池使用情况"""
        self.connection_usage.append({
            "timestamp": datetime.now().isoformat(),
            "checked_out": pool_status.get("checked_out", 0),
            "checked_in": pool_status.get("checked_in", 0),
            "overflow": pool_status.get("overflow", 0),
        })
        # 只保留最近100条记录
        if len(self.connection_usage) > 100:
            self.connection_usage = self.connection_usage[-100:]
    
    def record_error(self):
        """记录错误"""
        self.error_count += 1
    
    def get_performance_stats(self) -> dict:
        """获取性能统计"""
        if not self.query_times:
            return {"error": "No query data available"}
        
        return {
            "query_stats": {
                "count": len(self.query_times),
                "avg_time_ms": round(sum(self.query_times) / len(self.query_times), 2),
                "min_time_ms": round(min(self.query_times), 2),
                "max_time_ms": round(max(self.query_times), 2),
                "p95_time_ms": round(sorted(self.query_times)[int(len(self.query_times) * 0.95)], 2),
            },
            "connection_stats": {
                "recent_usage": self.connection_usage[-10:] if self.connection_usage else [],
                "total_errors": self.error_count,
            }
        }

# 创建性能监控器实例
db_performance_monitor = DatabasePerformanceMonitor()

async def get_database_performance() -> dict:
    """获取数据库性能统计"""
    return db_performance_monitor.get_performance_stats()


async def safe_dispose_engine(db_engine):
    """
    安全地关闭数据库引擎
    
    Args:
        db_engine: SQLAlchemy异步引擎实例
    """
    try:
        if db_engine:
            # dispose() 是同步方法，但可能涉及IO操作，使用run_in_executor避免阻塞
            await asyncio.to_thread(db_engine.dispose)
            logger.info("数据库引擎已安全关闭")
    except Exception as e:
        logger.error(f"关闭数据库引擎时出错: {e}")
        # 即使关闭失败也不抛出异常，避免影响应用关闭流程