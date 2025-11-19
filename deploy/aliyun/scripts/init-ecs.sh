#!/bin/bash

# 初始化脚本 - 阿里云 ECS 首次部署
# 此脚本在本地执行，用于初始化 ECS 服务器环境

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

log "开始初始化 ECS 服务器: ${ECS_HOST}"

# 检查并安装 Docker
log "检查 Docker..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << 'EOF'
    set -e
    
    if command -v docker &> /dev/null; then
        echo "Docker 已安装"
        docker --version
        systemctl is-active --quiet docker || systemctl start docker
    else
        echo "安装 Docker..."
        
        # 检测操作系统
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$ID
            VERSION=$VERSION_ID
        else
            echo "错误: 无法检测操作系统"
            exit 1
        fi
        
        # Ubuntu/Debian 安装
        if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
            # 更新包索引
            apt-get update
            
            # 安装必要的依赖
            apt-get install -y \
                ca-certificates \
                curl \
                gnupg \
                lsb-release
            
            # 添加 Docker 官方 GPG 密钥
            install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/${OS}/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            chmod a+r /etc/apt/keyrings/docker.gpg
            
            # 设置 Docker 仓库
            echo \
              "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${OS} \
              $(lsb_release -cs) stable" | \
              tee /etc/apt/sources.list.d/docker.list > /dev/null
            
            # 更新包索引
            apt-get update
            
            # 安装 Docker Engine
            apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            
            # 启动 Docker 服务
            systemctl start docker
            systemctl enable docker
            
        # CentOS/RHEL 安装
        elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
            # 安装必要的依赖
            yum install -y yum-utils
            
            # 添加 Docker 仓库
            yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            
            # 安装 Docker Engine
            yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            
            # 启动 Docker 服务
            systemctl start docker
            systemctl enable docker
            
        else
            echo "不支持的操作系统: $OS"
            exit 1
        fi
        
        # 验证安装
        docker --version
        docker compose version
        echo "Docker 安装完成！"
    fi
EOF

# 创建远程目录结构
log "创建远程目录结构..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << 'EOF'
    set -e
    DATA_DIR="/var/lib/knowhere"
    
    mkdir -p "${DATA_DIR}/data/postgres"
    mkdir -p "${DATA_DIR}/data/redis"
    mkdir -p "${DATA_DIR}/data/rabbitmq"
    mkdir -p "${DATA_DIR}/logs"
    mkdir -p "${DATA_DIR}/users"
    mkdir -p "/etc/letsencrypt"
    mkdir -p "/var/www/certbot"
    mkdir -p "${DATA_DIR}/nginx"
    mkdir -p "${DATA_DIR}/scripts"
    
    chmod 755 "${DATA_DIR}"
    chmod 755 "${DATA_DIR}/data"
    chmod 777 "${DATA_DIR}/logs"  # 允许容器内应用写入日志
    chmod 755 "${DATA_DIR}/users"
    chmod 755 "/etc/letsencrypt" 2>/dev/null || true
    chmod 755 "/var/www/certbot"
    chmod 755 "${DATA_DIR}/nginx"
    chmod 755 "${DATA_DIR}/scripts"
    
    # 设置 PostgreSQL 数据目录权限（postgres 用户 UID/GID 通常是 999）
    # 注意：如果目录已存在数据，需要先停止 postgres 容器再设置权限
    if [ -d "${DATA_DIR}/data/postgres" ] && [ -z "$(ls -A ${DATA_DIR}/data/postgres 2>/dev/null)" ]; then
        # 目录为空时，设置权限以便首次启动时 postgres 可以初始化
        chown -R 999:999 "${DATA_DIR}/data/postgres" 2>/dev/null || echo "注意: 无法设置 PostgreSQL 目录所有者，首次启动时会自动设置"
        chmod -R 700 "${DATA_DIR}/data/postgres"
    fi
    
    echo "目录创建完成"
EOF

# 传输 docker-compose 文件
log "传输 docker-compose 配置文件..."
scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
    "$DEPLOY_DIR/docker-compose.ecs.yml" \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/docker-compose.ecs.yml

# 传输 nginx 配置文件
log "传输 nginx 配置文件..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "mkdir -p /var/lib/knowhere/nginx"
scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
    "$DEPLOY_DIR/nginx/nginx.conf" \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/nginx/nginx.conf

# 传输部署脚本
log "传输部署脚本..."
scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
    "$DEPLOY_DIR/scripts/deploy-to-ecs.sh" \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/scripts/deploy-to-ecs.sh

scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
    "$DEPLOY_DIR/scripts/setup-ssl.sh" \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/scripts/setup-ssl.sh 2>/dev/null || warn "setup-ssl.sh 不存在，稍后创建"

scp $SSH_OPTIONS -o StrictHostKeyChecking=no \
    "$DEPLOY_DIR/scripts/renew-ssl.sh" \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/scripts/renew-ssl.sh 2>/dev/null || warn "renew-ssl.sh 不存在，稍后创建"

# 设置脚本执行权限
log "设置脚本执行权限..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << 'EOF'
    chmod +x /var/lib/knowhere/scripts/*.sh
    echo "权限设置完成"
EOF

# 检查 docker-compose（Docker 安装时已包含 docker-compose-plugin）
log "检查 docker-compose..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << 'EOF'
    if docker compose version &> /dev/null; then
        echo "docker-compose 已安装（Docker Compose Plugin）"
        docker compose version
    elif command -v docker-compose &> /dev/null; then
        echo "docker-compose 已安装（standalone）"
        docker-compose --version
    else
        echo "安装 docker-compose standalone..."
        # 安装 docker-compose standalone（作为备用）
        curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        docker-compose --version
    fi
EOF

# 检查 .env 文件
log "检查环境变量文件..."
if ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "[ -f /var/lib/knowhere/.env ]"; then
    warn ".env 文件已存在，跳过传输"
    log "如需更新 .env 文件，请手动传输:"
    log "  scp $SSH_OPTIONS .env ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/.env"
else
    warn ".env 文件不存在，请手动创建并传输:"
    log "  1. 基于 deploy/aliyun/.env.staging.template 创建 .env 文件"
    log "  2. 填写实际配置值"
    log "  3. 传输到服务器: scp $SSH_OPTIONS .env ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/.env"
fi

# 可选：预拉取基础服务镜像（加快后续部署速度）
log "预拉取基础服务镜像（可选，加快后续部署速度）..."
ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << 'EOF'
    set -e
    COMPOSE_FILE="/var/lib/knowhere/docker-compose.ecs.yml"
    
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo "docker-compose 文件不存在，跳过镜像预拉取"
        exit 0
    fi
    
    # 使用 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    cd "$(dirname "$COMPOSE_FILE")"
    
    echo "拉取基础服务镜像（postgres, redis, rabbitmq, nginx）..."
    if $DOCKER_COMPOSE -f "$COMPOSE_FILE" pull postgres redis rabbitmq nginx >/dev/null 2>&1; then
        echo "基础服务镜像预拉取完成"
    else
        echo "基础服务镜像预拉取完成（部分可能已存在或网络问题）"
    fi
EOF

log "初始化完成！"
log ""
log "后续步骤:"
log "  1. 准备 .env 文件并传输到服务器"
log "  2. SSH 到服务器执行 SSL 证书获取: /var/lib/knowhere/scripts/setup-ssl.sh"
log "  3. SSH 到服务器执行部署: /var/lib/knowhere/scripts/deploy-to-ecs.sh"
log "  4. 设置 SSL 证书自动续期 cron 任务"

