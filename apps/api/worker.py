#!/usr/bin/env python3
"""
Celery Worker 启动脚本
直接使用 python 命令启动 worker
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置 PYTHONPATH 环境变量
os.environ['PYTHONPATH'] = str(project_root)

from app.core.celery_app import celery_app

if __name__ == "__main__":
    # 设置环境变量
    os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")
    
    # 生成唯一的节点名称
    import socket
    hostname = socket.gethostname()
    pid = os.getpid()
    node_name = f"celery@{hostname}-{pid}"

    # 启动 worker，使用唯一的节点名称
    celery_app.worker_main([
        "worker", 
        "--loglevel=info", 
        "--concurrency=2",
        f"--hostname={node_name}"
    ])
