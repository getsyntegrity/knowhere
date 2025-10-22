#!/usr/bin/env python3
"""
Celery Worker 启动脚本
直接使用 python 命令启动 worker
"""
import os
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置 PYTHONPATH 环境变量
os.environ['PYTHONPATH'] = str(project_root)

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

    # 获取日志级别设置
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    
    # 启动 worker，使用唯一的节点名称
    celery_app.worker_main([
        "worker", 
        f"--loglevel={log_level}", 
        "--concurrency=2",
        f"--hostname={node_name}"
    ])
