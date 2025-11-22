#!/bin/bash

# SSL 证书设置脚本 - Let's Encrypt
# 此脚本在 ECS 服务器上执行，用于首次获取 SSL 证书

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
EMAIL=${SSL_EMAIL:-admin@knowhereto.com}
DOMAINS=${SSL_DOMAINS:-"api.knowhereto.com knowhereto.com"}

# 检查域名参数
if [ -z "$SSL_DOMAINS" ]; then
    warn "未设置 SSL_DOMAINS，使用默认域名: $DOMAINS"
    warn "如需自定义，请设置环境变量: export SSL_DOMAINS='api.knowhereto.com knowhereto.com'"
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
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y certbot
    elif command -v yum &> /dev/null; then
        yum install -y certbot
    else
        error "无法自动安装 certbot，请手动安装"
    fi
fi

# 构建 certbot 命令参数
CERTBOT_DOMAINS=""
for domain in $DOMAINS; do
    CERTBOT_DOMAINS="$CERTBOT_DOMAINS -d $domain"
done

# 获取证书（使用 standalone 模式，需要先停止 nginx）
log "获取 SSL 证书..."
log "注意: 此过程需要域名已正确解析到服务器 IP，且 80 端口可访问"

# 检查 nginx 是否运行
if docker ps | grep -q knowhere-nginx; then
    log "停止 nginx 容器以释放 80 端口..."
    docker stop knowhere-nginx || true
    NGINX_WAS_RUNNING=true
else
    NGINX_WAS_RUNNING=false
fi

# 使用 certbot 获取证书（使用默认路径 /etc/letsencrypt）
if certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    $CERTBOT_DOMAINS \
    --preferred-challenges http; then
    log "SSL 证书获取成功"
else
    error "SSL 证书获取失败"
fi

# 如果 nginx 之前在运行，重新启动
if [ "$NGINX_WAS_RUNNING" = true ]; then
    log "重新启动 nginx 容器..."
    cd /var/lib/knowhere
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose.ecs.yml up -d nginx
    else
        docker-compose -f docker-compose.ecs.yml up -d nginx
    fi
fi

# 检查证书文件
if [ -f "/etc/letsencrypt/live/api.knowhereto.com/fullchain.pem" ] || [ -f "/etc/letsencrypt/live/knowhereto.com/fullchain.pem" ]; then
    log "证书文件已生成"
    log "证书位置: /etc/letsencrypt/live/"
else
    warn "证书文件可能未正确生成，请检查"
    log "Let's Encrypt 默认证书路径: /etc/letsencrypt/live/"
fi

log "SSL 证书设置完成！"
log ""
log "后续步骤:"
log "  1. 确保 nginx 配置中的证书路径正确"
log "  2. 重启 nginx 容器使配置生效"
log "  3. 设置自动续期 cron 任务: /var/lib/knowhere/scripts/renew-ssl.sh"

