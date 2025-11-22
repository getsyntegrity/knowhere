#!/bin/bash

# 将本地 Docker 镜像导出并传输到服务器
# 适用于网络受限或需要加速部署的场景

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

# 服务器连接配置（可直接修改或从配置文件读取）
ECS_HOST=${ECS_HOST:-"8.134.142.218"}
ECS_USER=${ECS_USER:-"root"}
SSH_KEY_PATH="$SCRIPT_DIR/id_rsa"

# 加载配置文件（如果存在，会覆盖上面的默认值）
CONFIG_FILE="$DEPLOY_DIR/deploy-config.sh"
if [ -f "$CONFIG_FILE" ]; then
    log "加载配置文件: $CONFIG_FILE"
    source "$CONFIG_FILE"
    # 如果配置文件中指定了 SSH_KEY，使用配置文件中的路径
    if [ -n "$SSH_KEY" ]; then
        if [[ "$SSH_KEY" != /* ]] && [[ "$SSH_KEY" != ~* ]]; then
            SSH_KEY_PATH="$DEPLOY_DIR/$SSH_KEY"
        else
            SSH_KEY_PATH="${SSH_KEY/#\~/$HOME}"
        fi
    fi
fi

# SSH 连接配置
if [ -f "$SSH_KEY_PATH" ]; then
    SSH_OPTIONS="-i $SSH_KEY_PATH"
    log "使用 SSH 密钥: $SSH_KEY_PATH"
else
    warn "SSH 密钥文件不存在: $SSH_KEY_PATH"
    warn "将使用密码登录"
    SSH_OPTIONS=""
fi

SSH_TARGET="${ECS_USER}@${ECS_HOST}"
log "目标服务器: $SSH_TARGET"

# 要导出的镜像列表
IMAGES=(
    "postgres:15-alpine"
    "redis:7-alpine"
    "rabbitmq:3.12-management"
    "nginx:alpine"
)

# 检查是否提供了已导出的镜像文件
EXPORT_FILE=${1:-""}

if [ -n "$EXPORT_FILE" ] && [ -f "$EXPORT_FILE" ]; then
    # 使用用户提供的已导出镜像文件
    log "使用已导出的镜像文件: $EXPORT_FILE"
    EXPORT_SIZE=$(du -h "$EXPORT_FILE" | cut -f1)
    log "镜像文件大小: $EXPORT_SIZE"
else
    # 需要导出镜像
    log "开始导出并传输镜像到服务器: $SSH_TARGET"
    
    # 1. 检查本地镜像是否存在，不存在则拉取
    log "检查本地镜像..."
    for IMAGE in "${IMAGES[@]}"; do
        if docker image inspect "$IMAGE" &>/dev/null; then
            log "✓ 本地已存在: $IMAGE"
        else
            log "拉取镜像: $IMAGE"
            docker pull "$IMAGE" || error "无法拉取镜像: $IMAGE"
        fi
    done
    
    # 2. 导出镜像为 tar 文件
    log "导出镜像..."
    TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" EXIT
    EXPORT_FILE="$TEMP_DIR/images.tar"
    docker save "${IMAGES[@]}" -o "$EXPORT_FILE"
    EXPORT_SIZE=$(du -h "$EXPORT_FILE" | cut -f1)
    log "镜像导出完成，大小: $EXPORT_SIZE"
fi

# 3. 传输到服务器
log "传输镜像到服务器..."
REMOTE_TEMP="/tmp/knowhere-images-$(date +%s).tar"
scp $SSH_OPTIONS -o StrictHostKeyChecking=no "$EXPORT_FILE" $SSH_TARGET:${REMOTE_TEMP} || {
    error "镜像传输失败"
}

# 4. 在服务器上加载镜像
log "在服务器上加载镜像..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no $SSH_TARGET bash << EOF
    set -e
    log() {
        echo -e "\033[0;32m[\$(date +'%Y-%m-%d %H:%M:%S')] \$1\033[0m"
    }
    
    log "加载镜像..."
    docker load -i ${REMOTE_TEMP} || {
        echo "镜像加载失败"
        exit 1
    }
    
    log "清理临时文件..."
    rm -f ${REMOTE_TEMP}
    
    log "验证镜像..."
    docker images | grep -E "postgres|redis|rabbitmq|nginx" || true
    
    log "镜像加载完成！"
EOF

log "所有镜像已成功传输并加载到服务器！"
log ""
log "现在可以在服务器上运行部署脚本:"
log "  ssh $SSH_OPTIONS $SSH_TARGET '/var/lib/knowhere/scripts/deploy-to-ecs.sh'"
log ""
log "或者直接执行:"
log "  ssh $SSH_OPTIONS $SSH_TARGET"

