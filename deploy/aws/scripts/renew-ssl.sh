#!/bin/bash

# SSL 证书续期脚本 - Let's Encrypt
# 此脚本用于自动续期 SSL 证书，可通过 cron 定期执行

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
COMPOSE_FILE="/var/lib/knowhere/docker-compose.ec2.yml"
EMAIL=${SSL_EMAIL:-admin@knowhereto.ai}
CERT_PATH="/etc/letsencrypt/live"

# 检查 certbot
if ! command -v certbot &> /dev/null; then
    error "certbot 未安装"
fi

# 检查证书是否存在
if [ ! -d "$CERT_PATH" ]; then
    error "未找到证书目录: $CERT_PATH"
fi

log "检查 SSL 证书到期时间..."

# 检查证书是否需要续期（30 天内到期）
if certbot certificates 2>/dev/null | grep -q "30 days"; then
    log "证书即将到期，开始续期..."
    
    # 获取所有域名
    DOMAINS=$(certbot certificates 2>/dev/null | grep "Domains:" | sed 's/Domains: //' | tr ' ' '\n' | grep -v '^$' | tr '\n' ' ')
    
    if [ -z "$DOMAINS" ]; then
        error "无法获取域名列表"
    fi
    
    log "续期域名: $DOMAINS"
    
    # 停止 nginx 以释放 80 端口
    if docker ps | grep -q knowhere-nginx; then
        log "停止 nginx 容器..."
        docker stop knowhere-nginx || true
        NGINX_WAS_RUNNING=true
    else
        NGINX_WAS_RUNNING=false
    fi
    
    # 续期证书
    if certbot renew --standalone --non-interactive --agree-tos --email "$EMAIL"; then
        log "证书续期成功"
        
        # 重新启动 nginx
        if [ "$NGINX_WAS_RUNNING" = true ]; then
            log "重新启动 nginx 容器..."
            cd /var/lib/knowhere
            if docker compose version &> /dev/null; then
                docker compose -f "$COMPOSE_FILE" up -d nginx
            else
                docker-compose -f "$COMPOSE_FILE" up -d nginx
            fi
            
            # 等待 nginx 启动
            sleep 5
            
            # 检查 nginx 状态
            if docker ps | grep -q knowhere-nginx; then
                log "nginx 已重新启动"
            else
                warn "nginx 可能未正常启动，请检查"
            fi
        fi
        
        log "SSL 证书续期完成"
    else
        error "证书续期失败"
    fi
else
    log "证书尚未到期，无需续期"
    
    # 显示证书信息
    certbot certificates 2>/dev/null || true
fi

log "SSL 证书检查完成"

