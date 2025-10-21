#!/bin/bash
# 首次实例配置脚本
# 在EC2实例上运行，配置应用环境

set -e

# 配置变量
PROJECT_NAME="knowhere"
ENVIRONMENT="test"
APP_DIR="/opt/knowhere"
VENV_DIR="$APP_DIR/venv"
API_DIR="$APP_DIR/apps/api"
WEB_DIR="$APP_DIR/apps/web"

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

log "开始配置Knowhere应用环境..."

# 1. 创建Python虚拟环境
log "创建Python虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    log "Python虚拟环境创建完成"
else
    log "Python虚拟环境已存在"
fi

# 激活虚拟环境并升级pip
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel

# 2. 克隆代码仓库（如果不存在）
log "检查代码仓库..."
if [ ! -d "$API_DIR" ]; then
    log "代码仓库不存在，请先克隆代码到 $APP_DIR"
    log "例如: git clone https://github.com/your-org/knowhere.git $APP_DIR"
    exit 1
fi

# 3. 安装Python依赖
log "安装Python依赖..."
cd "$API_DIR"
pip install -r requirements.txt
log "Python依赖安装完成"

# 4. 安装Node.js依赖
log "安装Node.js依赖..."
if [ -d "$WEB_DIR" ]; then
    # 安装pnpm
    log "安装pnpm..."
    npm install -g pnpm
    
    # 使用pnpm安装依赖
    cd "$APP_DIR"
    CI=true pnpm install --no-frozen-lockfile
    log "Node.js依赖安装完成"
    
    # 构建Web应用
    if [ -d "$WEB_DIR" ]; then
        cd "$WEB_DIR"
        CI=true pnpm run build
        log "Web应用构建完成"
    fi
else
    warn "Web目录不存在，跳过Node.js依赖安装"
fi

# 5. 创建应用用户（如果不存在）
log "检查应用用户..."
if ! id "appuser" &>/dev/null; then
    useradd -m -s /bin/bash appuser
    log "应用用户创建完成"
else
    log "应用用户已存在"
fi

# 6. 设置目录权限
log "设置目录权限..."
chown -R appuser:appuser "$APP_DIR"
chmod -R 755 "$APP_DIR"

# 7. 创建日志目录
log "创建日志目录..."
mkdir -p "$APP_DIR/logs"
chown appuser:appuser "$APP_DIR/logs"
chmod 755 "$APP_DIR/logs"

# 8. 配置systemd服务
log "配置systemd服务..."
cp "$APP_DIR/deploy/aws-ec2/systemd/knowhere-api.service" /etc/systemd/system/
cp "$APP_DIR/deploy/aws-ec2/systemd/knowhere-web.service" /etc/systemd/system/
cp "$APP_DIR/deploy/aws-ec2/systemd/knowhere-worker.service" /etc/systemd/system/
cp "$APP_DIR/deploy/aws-ec2/systemd/knowhere-scheduler.service" /etc/systemd/system/

# 重新加载systemd
systemctl daemon-reload

# 9. 配置Nginx
log "配置Nginx..."
cp "$APP_DIR/deploy/aws-ec2/nginx/knowhere.conf" /etc/nginx/sites-available/
cp "$APP_DIR/deploy/aws-ec2/nginx/nginx.conf" /etc/nginx/nginx.conf
cp "$APP_DIR/deploy/aws-ec2/nginx/ssl-params.conf" /etc/nginx/ssl-params.conf

# 启用站点
ln -sf /etc/nginx/sites-available/knowhere.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试Nginx配置
nginx -t
if [ $? -eq 0 ]; then
    log "Nginx配置测试通过"
else
    error "Nginx配置测试失败"
fi

# 10. 创建环境变量文件
log "创建环境变量文件..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.template" "$APP_DIR/.env"
    chown appuser:appuser "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    log "环境变量文件已创建，请编辑 $APP_DIR/.env 填入实际配置"
else
    log "环境变量文件已存在"
fi

# 11. 配置CloudWatch Agent
log "配置CloudWatch Agent..."
if [ -f "/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json" ]; then
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
        -a fetch-config \
        -m ec2 \
        -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
        -s
    log "CloudWatch Agent配置完成"
else
    warn "CloudWatch Agent配置文件不存在"
fi

# 12. 启用服务
log "启用服务..."
systemctl enable knowhere-api
systemctl enable knowhere-web
systemctl enable knowhere-worker
systemctl enable knowhere-scheduler
systemctl enable nginx

log "服务已启用"

# 13. 创建健康检查脚本
log "创建健康检查脚本..."
cat > /usr/local/bin/knowhere-health-check.sh << 'EOF'
#!/bin/bash
# 健康检查脚本

API_URL="http://localhost:5005/health"
WEB_URL="http://localhost:3000"

# 检查API健康
if curl -f -s "$API_URL" > /dev/null; then
    echo "API: OK"
    API_STATUS=0
else
    echo "API: FAIL"
    API_STATUS=1
fi

# 检查Web健康
if curl -f -s "$WEB_URL" > /dev/null; then
    echo "Web: OK"
    WEB_STATUS=0
else
    echo "Web: FAIL"
    WEB_STATUS=1
fi

# 检查服务状态
if systemctl is-active --quiet knowhere-api; then
    echo "API Service: OK"
else
    echo "API Service: FAIL"
    API_STATUS=1
fi

if systemctl is-active --quiet knowhere-web; then
    echo "Web Service: OK"
else
    echo "Web Service: FAIL"
    WEB_STATUS=1
fi

if systemctl is-active --quiet knowhere-worker; then
    echo "Worker Service: OK"
else
    echo "Worker Service: FAIL"
fi

exit $((API_STATUS + WEB_STATUS))
EOF

chmod +x /usr/local/bin/knowhere-health-check.sh

# 14. 创建日志查看脚本
log "创建日志查看脚本..."
cat > /usr/local/bin/knowhere-logs.sh << 'EOF'
#!/bin/bash
# 日志查看脚本

case "$1" in
    "api")
        journalctl -u knowhere-api -f
        ;;
    "web")
        journalctl -u knowhere-web -f
        ;;
    "worker")
        journalctl -u knowhere-worker -f
        ;;
    "scheduler")
        journalctl -u knowhere-scheduler -f
        ;;
    "nginx")
        tail -f /var/log/nginx/*.log
        ;;
    "app")
        tail -f /opt/knowhere/logs/*.log
        ;;
    *)
        echo "用法: $0 {api|web|worker|scheduler|nginx|app}"
        echo "  api       - 查看API服务日志"
        echo "  web       - 查看Web服务日志"
        echo "  worker    - 查看Worker服务日志"
        echo "  scheduler - 查看Scheduler服务日志"
        echo "  nginx     - 查看Nginx日志"
        echo "  app       - 查看应用日志"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/knowhere-logs.sh

log "实例配置完成！"
log ""
log "下一步操作："
log "1. 编辑环境变量: sudo nano $APP_DIR/.env"
log "2. 启动服务: sudo systemctl start knowhere-api knowhere-web knowhere-worker"
log "3. 启动Nginx: sudo systemctl start nginx"
log "4. 检查状态: knowhere-health-check.sh"
log "5. 查看日志: knowhere-logs.sh api"
log ""
log "服务管理命令："
log "  sudo systemctl start|stop|restart|status knowhere-api"
log "  sudo systemctl start|stop|restart|status knowhere-web"
log "  sudo systemctl start|stop|restart|status knowhere-worker"
log "  sudo systemctl start|stop|restart|status knowhere-scheduler"
