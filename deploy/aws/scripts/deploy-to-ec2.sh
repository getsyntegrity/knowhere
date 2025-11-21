#!/bin/bash

# 部署脚本 - AWS EC2 Docker Compose 部署
# 此脚本在 EC2 服务器上执行，使用 docker-compose 管理所有服务

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

# 配置路径
COMPOSE_FILE="/var/lib/knowhere/docker-compose.ec2.yml"
ENV_FILE="/var/lib/knowhere/.env"
DATA_DIR="/var/lib/knowhere"

# 检查 docker 和 docker-compose
if ! command -v docker &> /dev/null; then
    error "Docker 未安装，请先安装 Docker"
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    error "docker-compose 未安装，请先安装 docker-compose"
fi

# 使用 docker compose 或 docker-compose
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 检查必要文件
if [ ! -f "$COMPOSE_FILE" ]; then
    error "docker-compose 文件不存在: $COMPOSE_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
    error "环境变量文件不存在: $ENV_FILE"
fi

# 创建必要的目录
log "创建数据目录..."
mkdir -p "${DATA_DIR}/data/postgres"
mkdir -p "${DATA_DIR}/data/redis"
mkdir -p "${DATA_DIR}/data/rabbitmq"
mkdir -p "${DATA_DIR}/logs"
mkdir -p "${DATA_DIR}/users"
mkdir -p "/etc/letsencrypt"
mkdir -p "/var/www/certbot"
mkdir -p "${DATA_DIR}/nginx"

# 设置目录权限
chmod 755 "${DATA_DIR}"
chmod 755 "${DATA_DIR}/data"
chmod 777 "${DATA_DIR}/logs"  # 允许容器内应用写入日志
chmod 777 "${DATA_DIR}/users"  # 允许容器内应用写入用户数据
chmod 755 "/etc/letsencrypt"
chmod 755 "/var/www/certbot"

# 设置 PostgreSQL 数据目录权限（postgres 用户 UID/GID 通常是 999）
log "设置 PostgreSQL 数据目录权限..."
if [ -d "${DATA_DIR}/data/postgres" ]; then
    # 如果 postgres 容器未运行，可以安全地设置权限
    if ! docker ps --format '{{.Names}}' | grep -q '^knowhere-postgres$'; then
        chown -R 999:999 "${DATA_DIR}/data/postgres" 2>/dev/null || warn "无法设置 PostgreSQL 目录所有者（可能需要手动设置）"
        chmod -R 700 "${DATA_DIR}/data/postgres"
    else
        warn "PostgreSQL 容器正在运行，跳过权限设置（容器会自动管理权限）"
    fi
fi

# 设置 Redis 数据目录权限（redis 用户 UID/GID 通常是 999）
log "设置 Redis 数据目录权限..."
if [ -d "${DATA_DIR}/data/redis" ]; then
    # 如果 redis 容器未运行，可以安全地设置权限
    if ! docker ps --format '{{.Names}}' | grep -q '^knowhere-redis$'; then
        chown -R 999:999 "${DATA_DIR}/data/redis" 2>/dev/null || warn "无法设置 Redis 目录所有者（可能需要手动设置）"
        chmod -R 755 "${DATA_DIR}/data/redis"
    else
        warn "Redis 容器正在运行，跳过权限设置（容器会自动管理权限）"
    fi
fi

# GitHub Container Registry 登录（如果需要）
GITHUB_USERNAME=${GITHUB_USERNAME:-}
GITHUB_TOKEN=${GITHUB_TOKEN:-}
REGISTRY="ghcr.io"

# 设置镜像名称环境变量（用于 docker-compose）
if [[ -n "$GITHUB_USERNAME" ]]; then
    export GHCR_IMAGE_BACKEND="ghcr.io/${GITHUB_USERNAME}/knowhere-backend:staging-latest"
    export GHCR_IMAGE_FRONTEND="ghcr.io/${GITHUB_USERNAME}/knowhere-frontend:staging-latest"
    export GHCR_IMAGE_WORKER="ghcr.io/${GITHUB_USERNAME}/knowhere-worker:staging-latest"
    
    log "登录到 GitHub Container Registry: ${REGISTRY}"
    if [ -n "$GITHUB_TOKEN" ]; then
        echo "$GITHUB_TOKEN" | docker login --username="$GITHUB_USERNAME" --password-stdin "$REGISTRY" 2>/dev/null || {
            warn "无法使用环境变量登录到 GHCR，尝试使用已保存的凭据"
            docker login "$REGISTRY" 2>/dev/null || {
                error "无法登录到 GHCR，请先手动登录: docker login $REGISTRY"
            }
        }
    else
        if [ -f ~/.docker/config.json ] && grep -q "$REGISTRY" ~/.docker/config.json 2>/dev/null; then
            log "检测到已保存的 GHCR 登录凭证"
        else
            warn "未设置 GHCR 登录凭据，尝试使用已保存的凭据"
            docker login "$REGISTRY" 2>/dev/null || {
                error "无法登录到 GHCR，请先手动登录: docker login $REGISTRY"
            }
        fi
    fi
else
    warn "未设置 GITHUB_USERNAME，使用默认镜像名称"
fi

# 拉取最新镜像
log "拉取最新镜像..."
cd "$(dirname "$COMPOSE_FILE")"

# 先拉取基础服务镜像（从 Docker Hub，无需登录）
log "拉取基础服务镜像（postgres, redis, rabbitmq, nginx）..."
$DOCKER_COMPOSE -f "$COMPOSE_FILE" pull postgres redis rabbitmq nginx || {
    warn "部分基础服务镜像拉取失败，继续部署..."
}

# 拉取应用服务镜像（从 GHCR，需要登录）
log "拉取应用服务镜像（api, web, worker）..."
$DOCKER_COMPOSE -f "$COMPOSE_FILE" pull api web worker || {
    warn "部分应用服务镜像拉取失败，继续部署..."
}

# 启动服务（零停机更新）
log "启动服务..."
if $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d; then
    log "服务启动成功"
else
    error "服务启动失败"
fi

# 等待服务就绪
log "等待服务就绪..."
sleep 10

# 检查服务状态
log "检查服务状态..."
$DOCKER_COMPOSE -f "$COMPOSE_FILE" ps

# 健康检查
log "执行健康检查..."
FAILED_SERVICES=()

check_service() {
    local SERVICE=$1
    local MAX_RETRIES=10
    local RETRY=0
    
    while [ $RETRY -lt $MAX_RETRIES ]; do
        if $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps "$SERVICE" | grep -q "Up"; then
            log "服务 $SERVICE 运行正常"
            return 0
        fi
        RETRY=$((RETRY + 1))
        sleep 2
    done
    
    warn "服务 $SERVICE 可能未正常运行"
    FAILED_SERVICES+=("$SERVICE")
    return 1
}

check_service postgres
check_service redis
check_service rabbitmq
check_service api
check_service web
check_service worker
check_service nginx

# 显示失败的服务日志
if [ ${#FAILED_SERVICES[@]} -gt 0 ]; then
    warn "以下服务可能存在问题: ${FAILED_SERVICES[*]}"
    for SERVICE in "${FAILED_SERVICES[@]}"; do
        log "查看 $SERVICE 服务日志:"
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" logs --tail 50 "$SERVICE"
    done
fi

# 清理未使用的镜像
log "清理未使用的镜像..."
docker image prune -f --filter "until=24h" || true

log "部署完成！"
log ""
log "常用命令:"
log "  查看所有服务状态: $DOCKER_COMPOSE -f $COMPOSE_FILE ps"
log "  查看服务日志: $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f [服务名]"
log "  重启服务: $DOCKER_COMPOSE -f $COMPOSE_FILE restart [服务名]"
log "  停止所有服务: $DOCKER_COMPOSE -f $COMPOSE_FILE down"
log "  停止并删除数据: $DOCKER_COMPOSE -f $COMPOSE_FILE down -v"
