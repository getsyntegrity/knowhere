import asyncio
import sys
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from app.core import image_cli as ImageCli
from app.core.config import redis_pool_manager
from app.core.database import engine, Base
from loguru import logger
from app.core.logging import setup_logging
from contextlib import asynccontextmanager
# ARQ依赖已移除，使用Celery替代
from app.core.config import settings
from app.api.api_router import api_router
from app.services.user.user_config_service import UserConfigService
from app.core.middleware import setup_cors, LoggingMiddleware
from app.core.users import get_user_manager
from app.core.jwt import auth_backend
from app.models.database.user import User
from app.models.schemas.user import UserCreate, UserUpdate, UserRead
from fastapi_users import FastAPIUsers
from uuid import UUID
from app.middleware.api_key_auth_middleware import api_key_auth_middleware
from app.middleware.moesif_middleware import MoesifMiddleware
from app.core.exception_handlers import setup_exception_handlers

setup_logging()
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用的生命周期管理
    """
    logger.info("知识库API服务开始启动...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 导入所有模型以确保它们被注册
    from app.models.database import user
    await redis_pool_manager.init_pool()
    logger.info("Redis 连接池已创建。")

    # worker = Worker(
    #     functions = [process_ai_query],
    #     redis_settings = settings.get_redis_settings(),
    #     max_jobs = 20,
    #     job_timeout = 60000  # 任务超时60000秒，这里的默认值是359.99秒，当然这是个治标不治本的方法，后续再做真实性能优化
    # )
    # worker_task  = asyncio.create_task(worker.main())
    # app.state.worker = worker

    ImageCli.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    # Redis连接池已通过redis_pool_manager初始化
    # app.state.redis_pool = redis_pool
    yield
    # Redis连接池关闭已通过redis_pool_manager处理
    # await app.state.redis_pool.close()
    # logger.info("Redis 连接池已关闭。")
    await engine.dispose()
    logger.info("数据库引擎连接池已关闭。")
    # if hasattr(app.state, 'worker'):
    #     logger.info("正在关闭后台Worker...")
    #     await app.state.worker.close()
    #     await worker_task
    #     logger.info("后台Worker已关闭。")

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        lifespan=lifespan,  # 绑定生命周期管理器
        docs_url="/docs",
        openapi_version="3.1.0",
        root_path="/api"
    )
    # 设置中间件
    setup_cors(app)
    app.add_middleware(LoggingMiddleware)
    
    # 添加Moesif API监控中间件
    app.add_middleware(MoesifMiddleware)
    
    # 添加API Key认证中间件（可选，根据需要启用）
    # app.add_middleware(api_key_auth_middleware)

    # 创建 FastAPI Users 实例
    fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

    # 注册 FastAPI Users 路由 - 这些路由已经在 auth.py 中注册了，不需要重复注册

    @app.get("/", tags=["Root"])
    async def read_root():
        return {"message": f"Welcome to {app.title} - 知识库API服务!"}
    
    # 注册其他 API 路由
    app.include_router(api_router)
    
    # 设置全局异常处理器
    setup_exception_handlers(app)
    
    return app

# Worker settings removed as DsTasks.py was deleted
app = create_app()

if __name__ == "__main__":
    logger.info("知识库API服务启动...")
    port = 5005
    reload = False  # 开启热更新
    host = "0.0.0.0"
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="debug")