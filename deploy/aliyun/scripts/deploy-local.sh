#!/bin/bash

# 本地部署脚本 - 阿里云 ECS Docker Compose 部署
# 此脚本在本地执行，用于传输配置并触发远程部署

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

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/.."

# 加载配置文件（如果存在）
CONFIG_FILE="$DEPLOY_DIR/deploy-config.sh"
if [ -f "$CONFIG_FILE" ]; then
    log "加载配置文件: $CONFIG_FILE"
    source "$CONFIG_FILE"
else
    warn "配置文件不存在: $CONFIG_FILE"
    warn "请复制 deploy-config.sh.example 为 deploy-config.sh 并填写配置"
    warn "或手动设置环境变量: ECS_HOST, ECS_USER 等"
fi

# 检查必要的环境变量
if [ -z "$ECS_HOST" ]; then
    error "ECS_HOST 环境变量未设置"
fi

if [ -z "$ECS_USER" ]; then
    error "ECS_USER 环境变量未设置"
fi

# SSH 密钥配置（可选）
SSH_KEY=${SSH_KEY:-}
if [ -n "$SSH_KEY" ]; then
    # 如果是相对路径，基于 DEPLOY_DIR 解析
    if [[ "$SSH_KEY" != /* ]] && [[ "$SSH_KEY" != ~* ]]; then
        SSH_KEY="$DEPLOY_DIR/$SSH_KEY"
    fi
    # 展开 ~ 路径
    SSH_KEY="${SSH_KEY/#\~/$HOME}"
    
    if [ -f "$SSH_KEY" ]; then
        KEY_PERMS=$(stat -f "%OLp" "$SSH_KEY" 2>/dev/null || stat -c "%a" "$SSH_KEY" 2>/dev/null)
        if [ "$KEY_PERMS" != "600" ] && [ "$KEY_PERMS" != "400" ]; then
            chmod 600 "$SSH_KEY" 2>/dev/null || warn "无法修改 SSH 密钥权限"
        fi
        SSH_OPTIONS="-i $SSH_KEY"
        log "使用 SSH 密钥: $SSH_KEY"
    else
        warn "SSH 密钥文件不存在: $SSH_KEY"
        SSH_OPTIONS=""
    fi
else
    SSH_OPTIONS=""
fi

log "开始部署到 ECS 服务器: ${ECS_HOST}"

# 传输更新的配置文件
log "传输更新的配置文件..."

# 传输 docker-compose 文件
if [ -f "$DEPLOY_DIR/docker-compose.ecs.yml" ]; then
    log "传输 docker-compose.ecs.yml..."
    scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
        "$DEPLOY_DIR/docker-compose.ecs.yml" \
        ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/docker-compose.ecs.yml
else
    warn "docker-compose.ecs.yml 不存在，跳过"
fi

# 传输 nginx 配置文件
if [ -f "$DEPLOY_DIR/nginx/nginx.conf" ]; then
    log "传输 nginx.conf..."
    ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "mkdir -p /var/lib/knowhere/nginx"
    scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
        "$DEPLOY_DIR/nginx/nginx.conf" \
        ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/nginx/nginx.conf
else
    warn "nginx.conf 不存在，跳过"
fi

# 传输部署脚本
if [ -f "$DEPLOY_DIR/scripts/deploy-to-ecs.sh" ]; then
    log "传输 deploy-to-ecs.sh..."
    scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
        "$DEPLOY_DIR/scripts/deploy-to-ecs.sh" \
        ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/scripts/deploy-to-ecs.sh
    ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} \
        "chmod +x /var/lib/knowhere/scripts/deploy-to-ecs.sh"
else
    warn "deploy-to-ecs.sh 不存在，跳过"
fi

# 检查 .env 文件是否需要更新
if [ -f ".env" ]; then
    read -p "是否更新 .env 文件? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "传输 .env 文件..."
        scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
            ".env" \
            ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/.env
        ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} \
            "chmod 600 /var/lib/knowhere/.env"
    fi
else
    warn ".env 文件不存在，跳过"
fi

# 执行远程部署
log "执行远程部署..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << EOF
    set -e
    export ACR_REGISTRY="${ACR_REGISTRY:-}"
    export ACR_NAMESPACE="${ACR_NAMESPACE:-knowhere}"
    export ALIYUN_ACR_USERNAME="${ALIYUN_ACR_USERNAME:-}"
    export ALIYUN_ACR_PASSWORD="${ALIYUN_ACR_PASSWORD:-}"
    
    /var/lib/knowhere/scripts/deploy-to-ecs.sh
EOF

if [ $? -eq 0 ]; then
    log "部署成功！"
    log ""
    log "查看服务状态:"
    if [ -n "$SSH_OPTIONS" ]; then
        log "  ssh $SSH_OPTIONS ${ECS_USER}@${ECS_HOST} 'cd /var/lib/knowhere && docker-compose -f docker-compose.ecs.yml ps'"
    else
        log "  ssh ${ECS_USER}@${ECS_HOST} 'cd /var/lib/knowhere && docker-compose -f docker-compose.ecs.yml ps'"
    fi
else
    error "部署失败"
fi

