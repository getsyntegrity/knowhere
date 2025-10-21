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
    
    # 运行数据库迁移
    from alembic.config import Config
    from alembic import command
    import subprocess
    import sys
    
    try:
        logger.info("开始运行数据库迁移...")
        # 使用subprocess运行alembic upgrade head
        result = subprocess.run([
            sys.executable, "-m", "alembic", "upgrade", "head"
        ], cwd=str(Path(__file__).parent), capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("数据库迁移完成")
        else:
            logger.error(f"数据库迁移失败: {result.stderr}")
            raise Exception(f"数据库迁移失败: {result.stderr}")
    except Exception as e:
        logger.error(f"运行数据库迁移时发生错误: {e}")
        raise
    
    # 创建数据库表（如果不存在）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 导入所有模型以确保它们被注册
    from app.models.database import user
    
    # 预热数据库连接池
    from app.core.database import prewarm_connection_pool
    await prewarm_connection_pool()
    logger.info("数据库连接池预热完成。")
    
    # 初始化Redis连接池
    await redis_pool_manager.init_pool()
    logger.info("Redis 连接池已创建。")

    # 初始化HTTP客户端
    ImageCli.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    logger.info("知识库API服务启动完成！")
    yield
    
    # 应用关闭时的清理工作
    logger.info("开始关闭服务...")
    await engine.dispose()
    logger.info("数据库引擎连接池已关闭。")
    logger.info("服务关闭完成。")

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
    fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

    # 注册 FastAPI Users 路由 - 这些路由已经在 auth.py 中注册了，不需要重复注册

    @app.get("/", tags=["Root"])
    async def read_root():
        return {"message": f"Welcome to {app.title} - 知识库API服务!"}
    
    @app.get("/health", tags=["Health"])
    async def health_check():
        """简单的健康检查端点"""
        return {"status": "healthy", "service": "knowhere-api"}
    
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