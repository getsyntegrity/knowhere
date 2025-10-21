#!/bin/bash
# 应用部署脚本
# 仅部署应用，不更新基础设施

set -e

# 配置变量
APP_DIR="/opt/knowhere"
API_DIR="$APP_DIR/apps/api"
WEB_DIR="$APP_DIR/apps/web"
VENV_DIR="$APP_DIR/venv"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    error "请使用sudo运行此脚本"
fi

log "开始部署Knowhere应用..."

# 1. 停止服务
log "停止服务..."
systemctl stop knowhere-api knowhere-web knowhere-worker knowhere-scheduler || true

# 2. 跳过备份（直接部署）
log "跳过备份，直接部署新版本..."

# 3. 拉取最新代码
log "拉取最新代码..."
cd "$APP_DIR"
if [ -d ".git" ]; then
    # 修复Git权限问题
    sudo -u appuser git config --global --add safe.directory /opt/knowhere
    sudo -u appuser git pull origin main
    log "代码已更新"
else
    warn "不是Git仓库，跳过代码更新"
fi

# 4. 更新Python依赖
log "更新Python依赖..."
if [ -d "$API_DIR" ]; then
    cd "$API_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -r requirements.txt
    log "Python依赖已更新"
fi

# 5. 更新Node.js依赖
log "更新Node.js依赖..."
if [ -d "$WEB_DIR" ]; then
    cd "$APP_DIR"
    CI=true pnpm install --no-frozen-lockfile
    log "Node.js依赖已更新"
    
    # 构建Web应用
    if [ -d "$WEB_DIR" ]; then
        cd "$WEB_DIR"
        CI=true pnpm run build
        log "Web应用构建完成"
    fi
fi

# 6. 运行数据库迁移
log "运行数据库迁移..."
if [ -d "$API_DIR" ]; then
    cd "$API_DIR"
    source "$VENV_DIR/bin/activate"
    python -m alembic upgrade head
    log "数据库迁移完成"
fi

# 7. 设置权限
log "设置权限..."
chown -R appuser:appuser "$APP_DIR"
chmod -R 755 "$APP_DIR"

# 8. 重新加载systemd配置
log "重新加载systemd配置..."
systemctl daemon-reload

# 9. 启动服务
log "启动服务..."
systemctl start knowhere-api
systemctl start knowhere-web
systemctl start knowhere-worker
systemctl start knowhere-scheduler

# 10. 重启Nginx
log "重启Nginx..."
systemctl reload nginx

# 11. 等待服务启动
log "等待服务启动..."
sleep 10

# 12. 健康检查
log "执行健康检查..."
if /usr/local/bin/knowhere-health-check.sh; then
    log "健康检查通过"
else
    warn "健康检查失败，请检查服务状态"
fi

# 13. 显示服务状态
log "服务状态："
systemctl status knowhere-api --no-pager -l
systemctl status knowhere-web --no-pager -l
systemctl status knowhere-worker --no-pager -l

log "应用部署完成！"
log ""
log "服务管理命令："
log "  sudo systemctl start|stop|restart|status knowhere-api"
log "  sudo systemctl start|stop|restart|status knowhere-web"
log "  sudo systemctl start|stop|restart|status knowhere-worker"
log ""
log "查看日志："
log "  knowhere-logs.sh api"
log "  knowhere-logs.sh web"
log "  knowhere-logs.sh worker"
