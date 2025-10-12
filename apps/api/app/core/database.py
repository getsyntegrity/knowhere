from contextlib import asynccontextmanager
from typing import AsyncGenerator, TypeVar, Callable, Awaitable

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import logging
logger = logging.getLogger(__name__)

# 创建 SQLAlchemy 异步引擎
from app.core.constants import ProcessingConstants

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True, # 取消注释以在控制台打印 SQL 语句，用于调试
    pool_recycle = ProcessingConstants.DB_POOL_RECYCLE,
    pool_size = ProcessingConstants.DB_POOL_SIZE,
    max_overflow = ProcessingConstants.DB_MAX_OVERFLOW,
    pool_pre_ping = True,
    connect_args={"connect_timeout": ProcessingConstants.DB_CONNECT_TIMEOUT}

)
# 创建异步会话工厂
AsyncSessionFactory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # 防止在提交后 ORM 对象过期
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
# 创建一个App上下文管理器，用于在无法传入db参数时执行数据库操作
@asynccontextmanager
async def get_db_context():
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
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
        from app.models.database import user, api_key, subscription, credits_transaction, usage_log
        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)