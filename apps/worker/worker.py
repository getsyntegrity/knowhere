#!/usr/bin/env python3
"""
Celery Worker 启动脚本
直接使用 python 命令启动 worker
"""
import os
import sys
import asyncio

# 从共享包导入
from shared.core.celery_app import celery_app
from shared.core.config import redis_pool_manager
from shared.core.logging import setup_logging
from loguru import logger

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
        "--concurrency=8",
        f"--hostname={node_name}"
    ])
