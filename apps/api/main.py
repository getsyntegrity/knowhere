import asyncio
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# 从共享包导入
from shared.core.config import redis_pool_manager, settings
from shared.core.database import engine, Base, safe_dispose_engine
from shared.core.logging import setup_logging
from shared.models.database.user import User
from shared.models.schemas.user import UserCreate, UserUpdate, UserRead

# 从本地 API 项目导入
from loguru import logger
from contextlib import asynccontextmanager
from app.api.api_router import api_router
from app.services.user.user_config_service import UserConfigService
from app.core.middleware import setup_cors, LoggingMiddleware
from app.core.users import get_user_manager
from app.core.jwt import auth_backend
from app.core.image_cli import ImageCli
from app.middleware.api_key_auth_middleware import api_key_auth_middleware
from app.middleware.moesif_middleware import MoesifMiddleware
from app.core.exception_handlers import setup_exception_handlers
from fastapi_users import FastAPIUsers
from uuid import UUID

# 动态导入 API 服务特定的 Celery 任务模块
# 这些模块不在共享包中，而是在 API 服务本地
try:
    import app.core.tasks.state_machine_tasks
    import app.core.tasks.webhook_tasks
    logger.info("成功导入 API 服务特定的 Celery 任务模块")
except ImportError as e:
    logger.warning(f"无法导入某些 Celery 任务模块: {e}")
    logger.warning("部分 Celery 任务可能不可用")

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
    from shared.models.database import user
    
    # 预热数据库连接池
    from shared.core.database import prewarm_connection_pool
    await prewarm_connection_pool()
    logger.info("数据库连接池预热完成。")
    
    # 初始化Redis连接池
    await redis_pool_manager.init_pool()
    logger.info("Redis 连接池已创建。")

    # 初始化HTTP客户端
    ImageCli.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    # 启动消息消费者（仅在API服务中运行）
    try:
        from app.services.messaging_service import messaging_service
        await messaging_service.start()
        logger.info("消息消费者已启动")
    except Exception as e:
        logger.error(f"启动消息消费者失败: {e}")
        # 消息消费者启动失败不应该阻止API服务启动
    
    logger.info("知识库API服务启动完成！")
    yield
    
    # 停止消息消费者
    try:
        from app.services.messaging_service import messaging_service
        await messaging_service.stop()
    except Exception as e:
        logger.error(f"停止消息消费者失败: {e}")
    
    # 应用关闭时的清理工作
    logger.info("开始关闭服务...")
    await safe_dispose_engine(engine)
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
