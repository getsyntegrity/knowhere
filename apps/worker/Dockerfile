# Worker服务Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制共享包代码（保持目录结构）
COPY packages/shared-python/app /app/shared/app

# 复制Worker服务依赖
COPY apps/worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制Worker服务代码
COPY apps/worker/ .

# 设置PYTHONPATH：共享包路径 + 服务路径
ENV PYTHONPATH=/app:/app/shared
ENV PYTHONUNBUFFERED=1

# 创建非root用户
RUN useradd --create-home --shell /bin/bash appuser
RUN chown -R appuser:appuser /app
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "from app.core.celery_app import celery_app; celery_app.control.inspect().stats()" || exit 1

# 默认命令 - 启动Worker
CMD ["python", "worker.py"]

