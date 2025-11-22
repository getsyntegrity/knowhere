#!/bin/bash

# SSL 证书设置脚本 - Let's Encrypt
# 此脚本在 EC2 服务器上执行，用于首次获取 SSL 证书

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# 配置
SSL_DIR="/etc/letsencrypt"
WEBROOT="/var/www/certbot"
EMAIL=${SSL_EMAIL:-admin@knowhereto.ai}
DOMAINS=${SSL_DOMAINS:-"apitest.knowhereto.ai test.knowhereto.ai"}

# 检查域名参数
if [ -z "$SSL_DOMAINS" ]; then
    warn "未设置 SSL_DOMAINS，使用默认域名: $DOMAINS"
    warn "如需自定义，请设置环境变量: export SSL_DOMAINS='apitest.knowhereto.ai test.knowhereto.ai'"
fi

log "开始设置 SSL 证书"
log "域名: $DOMAINS"
log "邮箱: $EMAIL"

# 创建必要目录
mkdir -p "$SSL_DIR"
mkdir -p "$WEBROOT/.well-known/acme-challenge"
chmod -R 755 "$WEBROOT"
chmod -R 755 "$SSL_DIR"

# 检查 certbot 是否安装
if ! command -v certbot &> /dev/null; then
    log "安装 certbot..."
    
    # 检测操作系统
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        error "无法检测操作系统"
    fi
    
    # Ubuntu/Debian 安装
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        apt-get update
        apt-get install -y certbot
    # Amazon Linux 2 安装
    elif [ "$OS" = "amzn" ]; then
        yum install -y certbot
    # CentOS/RHEL 安装
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        yum install -y certbot
    else
        error "不支持的操作系统: $OS"
    fi
fi

# 检查 nginx 是否正在运行
if docker ps | grep -q knowhere-nginx; then
    log "停止 nginx 容器以释放 80 端口..."
    docker stop knowhere-nginx || true
    NGINX_WAS_RUNNING=true
else
    NGINX_WAS_RUNNING=false
fi

# 获取证书
log "获取 SSL 证书..."
if certbot certonly --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d $(echo $DOMAINS | tr ' ' ','); then
    log "SSL 证书获取成功"
else
    error "SSL 证书获取失败"
fi

# 重新启动 nginx（如果之前正在运行）
if [ "$NGINX_WAS_RUNNING" = true ]; then
    log "重新启动 nginx 容器..."
    cd /var/lib/knowhere
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose.ec2.yml up -d nginx
    else
        docker-compose -f docker-compose.ec2.yml up -d nginx
    fi
fi

log "SSL 证书设置完成！"
log "证书位置: $SSL_DIR/live/"

