import asyncio
import os
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# 从共享包导入
from shared.core.config import redis_pool_manager, settings
from shared.core.database import engine, Base, safe_dispose_engine
from shared.core.logging import setup_logging
# from shared.models.database.user import User
# from shared.models.schemas.user import UserCreate, UserUpdate, UserRead

# 从本地 API 项目导入
from loguru import logger
from contextlib import asynccontextmanager
from app.api.api_router import api_router
from app.core.middleware import setup_cors, LoggingMiddleware
# from app.core.users import get_user_manager
# from app.core.jwt import auth_backend
from app.core.image_cli import ImageCli
# from app.middleware.api_key_auth_middleware import api_key_auth_middleware
from app.middleware.moesif_middleware import MoesifMiddleware
from app.core.exception_handlers import setup_exception_handlers
# from fastapi_users import FastAPIUsers
# from uuid import UUID

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用的生命周期管理
    """
    # 运行数据库迁移
    import subprocess
    import sys
    
    try:
        logger.info("start running database migration...")
        result = subprocess.run([
            sys.executable, "-m", "alembic", "upgrade", "heads"
        ], cwd=str(Path(__file__).parent), capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("database migration completed")
        else:
            logger.error(f"database migration failed: {result.stderr}")
            raise Exception(f"database migration failed: {result.stderr}")
    except Exception as e:
        logger.error(f"running database migration failed: {e}")
        raise

    from shared.core.database import prewarm_connection_pool
    await prewarm_connection_pool()
    logger.info("database connection pool warmed up.")
    
    await redis_pool_manager.init_pool()
    logger.info("Redis connection pool created.")

    ImageCli.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    try:
        from app.services.messaging_service import messaging_service
        await messaging_service.start()
        logger.info("message consumer started")
    except Exception as e:
        logger.error(f"message consumer start failed: {e}")
    
    logger.info("knowledge library API service started!")
    yield
    
    try:
        from app.services.messaging_service import messaging_service
        await messaging_service.stop()
    except Exception as e:
        logger.error(f"message consumer stop failed: {e}")
    
    logger.info("knowledge library API service stopped!")
    await safe_dispose_engine(engine)
    logger.info("database engine connection pool disposed.")
    logger.info("service stopped.")

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

    # 添加API Key认证中间件
    # app.add_middleware(api_key_auth_middleware)

    # 创建 FastAPI Users 实例
    # fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

    # 注册 FastAPI Users 路由 - 这些路由已经在 auth.py 中注册了，不需要重复注册

    @app.get("/", tags=["Root"])
    async def read_root():
        return {"message": f"Welcome to {app.title} - 知识库API服务!"}
    
    @app.api_route("/health", methods=["GET", "HEAD"], tags=["Health"])
    async def health_check():
        """简单的健康检查端点，支持 GET 和 HEAD 方法"""
        version = os.getenv("APP_VERSION", settings.APP_VERSION)
        return {
            "status": "healthy",
            "service": "knowhere-api",
            "version": version
        }
    
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
