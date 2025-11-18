#!/bin/bash

# 部署脚本 - AWS EC2 固定服务器
# 用于 staging 分支部署到固定 EC2 服务器

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

# 检查必要的环境变量
if [ -z "$EC2_HOST" ]; then
    error "EC2_HOST 环境变量未设置"
fi

if [ -z "$EC2_USER" ]; then
    error "EC2_USER 环境变量未设置"
fi

if [ -z "$IMAGE_TAG" ]; then
    error "IMAGE_TAG 环境变量未设置"
fi

if [ -z "$GITHUB_USERNAME" ]; then
    error "GITHUB_USERNAME 环境变量未设置"
fi

# 镜像仓库配置
REGISTRY="ghcr.io"
BACKEND_IMAGE="${REGISTRY}/${GITHUB_USERNAME}/knowhere-backend"
FRONTEND_IMAGE="${REGISTRY}/${GITHUB_USERNAME}/knowhere-frontend"
WORKER_IMAGE="${REGISTRY}/${GITHUB_USERNAME}/knowhere-worker"

log "开始部署到 EC2 服务器: ${EC2_HOST}"
log "镜像标签: ${IMAGE_TAG}"
log "后端镜像: ${BACKEND_IMAGE}:${IMAGE_TAG}"
log "前端镜像: ${FRONTEND_IMAGE}:${IMAGE_TAG}"
log "Worker镜像: ${WORKER_IMAGE}:${IMAGE_TAG}"

# SSH 部署函数
deploy_service() {
    local SERVICE_NAME=$1
    local IMAGE_NAME=$2
    local CONTAINER_NAME=$3
    local PORT=$4
    
    log "部署 ${SERVICE_NAME} 服务..."
    
    ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} bash << EOF
        set -e
        
        # 登录到 GitHub Container Registry
        # 注意：GITHUB_TOKEN 需要通过 SSH 传递，或使用服务器上已配置的凭据
        if command -v docker &> /dev/null; then
            # 尝试使用已保存的凭据或配置的 token
            docker login ${REGISTRY} -u ${GITHUB_USERNAME} 2>/dev/null || {
                echo "警告: 无法登录到 ${REGISTRY}，请确保服务器上已配置 GitHub token"
                echo "可以在服务器上运行: echo \$GITHUB_TOKEN | docker login ${REGISTRY} -u ${GITHUB_USERNAME} --password-stdin"
            }
        else
            echo "错误: Docker 未安装"
            exit 1
        fi
        
        # 停止并删除旧容器
        docker stop ${CONTAINER_NAME} 2>/dev/null || true
        docker rm ${CONTAINER_NAME} 2>/dev/null || true
        
        # 拉取新镜像
        docker pull ${IMAGE_NAME}:${IMAGE_TAG} || {
            echo "警告: 无法拉取镜像 ${IMAGE_NAME}:${IMAGE_TAG}，尝试使用 latest 标签"
            docker pull ${IMAGE_NAME}:staging-latest || {
                echo "错误: 无法拉取镜像"
                exit 1
            }
            IMAGE_TAG_ACTUAL="staging-latest"
        }
        
        # 运行新容器
        docker run -d \\
            --name ${CONTAINER_NAME} \\
            --restart unless-stopped \\
            -p ${PORT}:${PORT} \\
            ${IMAGE_NAME}:\${IMAGE_TAG_ACTUAL:-${IMAGE_TAG}}
        
        # 清理旧镜像
        docker image prune -f
        
        echo "${SERVICE_NAME} 部署完成"
EOF
    
    if [ $? -eq 0 ]; then
        log "${SERVICE_NAME} 部署成功"
    else
        error "${SERVICE_NAME} 部署失败"
    fi
}

# 部署所有服务
log "开始部署所有服务..."

# 注意：这里需要根据实际需求调整端口和容器配置
# 部署后端服务
deploy_service "Backend" "${BACKEND_IMAGE}" "knowhere-backend" "5005"

# 部署前端服务
deploy_service "Frontend" "${FRONTEND_IMAGE}" "knowhere-frontend" "3000"

# 部署 Worker 服务（如果需要）
# deploy_service "Worker" "${WORKER_IMAGE}" "knowhere-worker" "8000"

log "所有服务部署完成！"
log "请检查服务状态: ssh ${EC2_USER}@${EC2_HOST} 'docker ps'"

