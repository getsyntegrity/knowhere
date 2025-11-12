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

from app.core.celery_app import celery_app
from app.core.config import redis_pool_manager
from app.core.logging import setup_logging
from loguru import logger

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

    # 动态导入 kb_tasks（仅在 Worker 服务中使用）
    # 注意：kb_tasks 不在共享包中，而是在 worker 本地路径中
    try:
        import app.core.tasks.kb_tasks
        logger.info("成功导入 kb_tasks 模块")
    except ImportError as e:
        logger.warning(f"无法导入 kb_tasks 模块: {e}")
        logger.warning("kb_tasks 相关任务将不可用")
    
    # 获取日志级别设置
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    
    # 启动 worker，使用唯一的节点名称
    celery_app.worker_main([
        "worker", 
        f"--loglevel={log_level}", 
        "--concurrency=2",
        f"--hostname={node_name}"
    ])

