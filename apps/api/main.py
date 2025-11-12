import asyncio
import sys
import os
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# 设置PYTHONPATH以包含共享包路径（必须在所有导入之前）
project_root = Path(__file__).parent.resolve()
shared_python_path = project_root.parent.parent / "packages" / "shared-python"
shared_python_path = shared_python_path.resolve()

# 关键：需要同时支持共享包和服务自己的app模块
# 策略：共享包路径优先（用于共享代码），服务路径其次（用于服务专用代码）
shared_path_str = str(shared_python_path)
project_path_str = str(project_root)

# 清除可能已缓存的app模块（如果之前从错误的位置导入了）
if 'app' in sys.modules:
    del sys.modules['app']
    # 同时清除app的子模块
    modules_to_remove = [key for key in sys.modules.keys() if key.startswith('app.')]
    for key in modules_to_remove:
        del sys.modules[key]

# 移除可能存在的路径，避免重复
if shared_path_str in sys.path:
    sys.path.remove(shared_path_str)
if project_path_str in sys.path:
    sys.path.remove(project_path_str)

# 按优先级顺序插入：共享包优先，然后是项目根目录
# 这样：共享包的app.core会被优先找到，但服务自己的app.api也能被找到
if shared_python_path.exists():
    sys.path.insert(0, shared_path_str)
if project_root.exists():
    sys.path.insert(1 if shared_python_path.exists() else 0, project_path_str)

# 设置环境变量（共享包路径优先）
current_pythonpath = os.environ.get('PYTHONPATH', '')
if shared_path_str not in current_pythonpath:
    os.environ['PYTHONPATH'] = f"{shared_path_str}:{project_path_str}:{current_pythonpath}" if current_pythonpath else f"{shared_path_str}:{project_path_str}"

def extend_module_path(module, relative_path: str):
    """
    扩展模块的 __path__ 以包含 API 服务的路径
    
    Args:
        module: 要扩展的模块对象
        relative_path: 相对于 app/ 的路径，例如 "core", "services/messaging"
    """
    api_path = project_root / "app" / relative_path
    shared_path = shared_python_path / "app" / relative_path
    
    if api_path.exists() and hasattr(module, '__path__'):
        # 确保共享包路径在最前面（优先查找共享代码）
        shared_path_str = str(shared_path)
        api_path_str = str(api_path)
        
        if shared_path_str in module.__path__:
            module.__path__.remove(shared_path_str)
        module.__path__.insert(0, shared_path_str)
        
        # API服务的路径在后面（用于查找服务专用模块）
        if api_path_str not in module.__path__:
            module.__path__.append(api_path_str)

# 扩展各个模块的 __path__ 以支持共享包和服务专用代码
# 注意：共享包的路径应该在前面（优先），API服务的路径在后面（用于查找服务专用模块）

# 扩展 app.__path__
import app
extend_module_path(app, "")

# 扩展 app.core.__path__
import app.core
extend_module_path(app.core, "core")

# 扩展 app.core.tasks.__path__
import app.core.tasks
extend_module_path(app.core.tasks, "core/tasks")

# 扩展 app.services.__path__
import app.services
extend_module_path(app.services, "services")

# 扩展 app.services.messaging.__path__
import app.services.messaging
extend_module_path(app.services.messaging, "services/messaging")

# 现在可以安全地从共享包导入
from app.core.config import redis_pool_manager, settings
from app.core.database import engine, Base, safe_dispose_engine

# 注意：image_cli是API专用的，需要从本地API项目的app.core导入
# 由于共享包的app.core已经在sys.modules中，我们需要直接导入本地模块
import importlib.util
image_cli_path = project_root / "app" / "core" / "image_cli.py"
if image_cli_path.exists():
    spec = importlib.util.spec_from_file_location("app.core.image_cli", image_cli_path)
    image_cli_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(image_cli_module)
    ImageCli = image_cli_module
else:
    raise ImportError(f"无法找到image_cli模块: {image_cli_path}")
from loguru import logger
from app.core.logging import setup_logging
from contextlib import asynccontextmanager
# ARQ依赖已移除，使用Celery替代
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

# 动态导入 API 服务特定的 Celery 任务模块
# 这些模块不在共享包中，而是在 API 服务本地
# 注意：message_handlers 不再是 Celery 任务，由 MessageConsumer 直接调用
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