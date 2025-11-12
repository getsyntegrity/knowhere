#!/usr/bin/env python3
"""
Celery Worker 启动脚本
直接使用 python 命令启动 worker
"""
import os
import sys
import asyncio
from pathlib import Path

# 设置 Python 路径以包含共享包
# 从当前文件位置计算 monorepo 根目录
project_root = Path(__file__).parent  # apps/worker
shared_python_path = project_root.parent.parent / "packages" / "shared-python"

# 确保共享包路径优先（移除可能存在的路径，然后重新插入到最前面）
shared_path_str = str(shared_python_path)
project_path_str = str(project_root)

# 清除可能已缓存的 app 模块（如果之前从错误的位置导入了）
if 'app' in sys.modules:
    del sys.modules['app']
    # 同时清除 app 的子模块
    modules_to_remove = [key for key in sys.modules.keys() if key.startswith('app.')]
    for key in modules_to_remove:
        del sys.modules[key]

# 移除可能存在的路径，避免重复
if shared_path_str in sys.path:
    sys.path.remove(shared_path_str)
if project_path_str in sys.path:
    sys.path.remove(project_path_str)

# 按优先级顺序插入：共享包优先，然后是项目根目录
if shared_python_path.exists():
    sys.path.insert(0, shared_path_str)
if project_root.exists():
    sys.path.insert(1 if shared_python_path.exists() else 0, project_path_str)

def extend_module_path(module, relative_path: str):
    """
    扩展模块的 __path__ 以包含 Worker 服务的路径
    
    Args:
        module: 要扩展的模块对象
        relative_path: 相对于 app/ 的路径，例如 "core", "core/tasks"
    """
    worker_path = project_root / "app" / relative_path
    shared_path = shared_python_path / "app" / relative_path
    
    if worker_path.exists() and hasattr(module, '__path__'):
        # 确保共享包路径在最前面（优先查找共享代码）
        shared_path_str = str(shared_path)
        worker_path_str = str(worker_path)
        
        if shared_path_str in module.__path__:
            module.__path__.remove(shared_path_str)
        module.__path__.insert(0, shared_path_str)
        
        # Worker服务的路径在后面（用于查找服务专用模块）
        if worker_path_str not in module.__path__:
            module.__path__.append(worker_path_str)

# 扩展各个模块的 __path__ 以支持共享包和服务专用代码
# 注意：共享包的路径应该在前面（优先），Worker服务的路径在后面（用于查找服务专用模块）

# 扩展 app.__path__
import app
extend_module_path(app, "")

# 扩展 app.core.__path__
import app.core
extend_module_path(app.core, "core")

# 扩展 app.services.__path__（用于查找共享包中的服务模块如redis、storage、messaging）
import app.services
extend_module_path(app.services, "services")

# 扩展 app.core.tasks.__path__（用于查找已迁移的kb_tasks）
import app.core.tasks
extend_module_path(app.core.tasks, "core/tasks")

from app.core.celery_app import celery_app
from app.core.config import redis_pool_manager
from app.core.logging import setup_logging
from loguru import logger

# 扩展 app.services 以支持从API服务导入ai模块
# 需要在worker中也能访问API服务的ai模块
api_root = project_root.parent / "api"
api_services_path = api_root / "app" / "services"
if api_services_path.exists():
    api_services_path_str = str(api_services_path)
    if hasattr(app.services, '__path__') and api_services_path_str not in app.services.__path__:
        app.services.__path__.append(api_services_path_str)
        logger.info(f"已添加API服务路径到app.services: {api_services_path_str}")

# 显式导入 kb_tasks 模块以注册任务
# 注意：必须在导入 celery_app 之后导入，确保任务装饰器能够正确注册
import app.core.tasks.kb_tasks

async def init_redis():
    """初始化Redis连接池"""
    try:
        await redis_pool_manager.init_pool()
        logger.info("Celery Worker Redis 连接池初始化成功")
    except Exception as e:
        logger.error(f"Celery Worker Redis 初始化失败: {e}")
        raise

if __name__ == "__main__":
    # 设置环境变量
    os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")
    
    # 初始化日志配置
    setup_logging()
    logger.info("Celery Worker 日志配置初始化完成")
    
    # 初始化Redis连接池
    try:
        asyncio.run(init_redis())
    except Exception as e:
        logger.error(f"Worker启动失败: {e}")
        sys.exit(1)
    
    # 生成唯一的节点名称
    import socket
    hostname = socket.gethostname()
    pid = os.getpid()
    node_name = f"celery@{hostname}-{pid}"
    
    # 获取日志级别设置
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    
    # 启动 worker，使用唯一的节点名称
    celery_app.worker_main([
        "worker", 
        f"--loglevel={log_level}", 
        "--concurrency=2",
        f"--hostname={node_name}"
    ])

