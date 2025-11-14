#!/bin/sh
# API服务启动脚本 - 处理volume权限并启动服务

# 确保目录存在（volume挂载后）
mkdir -p /tmp/users /tmp/aismart_bid

# 尝试设置权限（如果以root运行）
if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /tmp/users /tmp/aismart_bid 2>/dev/null || true
    chmod -R 777 /tmp/users /tmp/aismart_bid 2>/dev/null || true
    # 切换到appuser
    exec su-exec appuser python main.py
else
    # 已经是appuser，直接运行
    exec python main.py
fi

