#!/bin/bash

# 部署脚本 - 阿里云 ECS 固定服务器
# 用于将应用部署到阿里云 ECS 服务器
# 支持 ACR 和 GHCR 两种镜像仓库

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
if [ -z "$ECS_HOST" ]; then
    error "ECS_HOST 环境变量未设置"
fi

if [ -z "$ECS_USER" ]; then
    error "ECS_USER 环境变量未设置"
fi

if [ -z "$IMAGE_TAG" ]; then
    error "IMAGE_TAG 环境变量未设置"
fi

# SSH 密钥配置（可选）
SSH_KEY=${SSH_KEY:-}
if [ -n "$SSH_KEY" ] && [ -f "$SSH_KEY" ]; then
    # 检查并修复 SSH 密钥权限
    KEY_PERMS=$(stat -f "%OLp" "$SSH_KEY" 2>/dev/null || stat -c "%a" "$SSH_KEY" 2>/dev/null)
    if [ "$KEY_PERMS" != "600" ] && [ "$KEY_PERMS" != "400" ]; then
        chmod 600 "$SSH_KEY" 2>/dev/null || warn "无法修改 SSH 密钥权限，请手动执行: chmod 600 $SSH_KEY"
    fi
    SSH_OPTIONS="-i $SSH_KEY"
else
    SSH_OPTIONS=""
fi

# 镜像仓库配置：优先使用 ACR，如果没有配置则使用 GHCR
ACR_REGISTRY=${ACR_REGISTRY:-}
ACR_NAMESPACE=${ACR_NAMESPACE:-knowhere}
GITHUB_USERNAME=${GITHUB_USERNAME:-}

if [[ -n "$ACR_REGISTRY" ]]; then
    # 使用 ACR 镜像仓库
    REGISTRY="$ACR_REGISTRY"
    REGISTRY_FULL="$ACR_REGISTRY/$ACR_NAMESPACE"
    USE_ACR=true
    log "使用 ACR 镜像仓库: ${REGISTRY_FULL}"
    
    if [ -z "$ACR_NAMESPACE" ]; then
        error "使用 ACR 时，ACR_NAMESPACE 环境变量必须设置"
    fi
    
    BACKEND_IMAGE="${REGISTRY_FULL}/knowhere-backend"
    FRONTEND_IMAGE="${REGISTRY_FULL}/knowhere-frontend"
    WORKER_IMAGE="${REGISTRY_FULL}/knowhere-worker"
elif [[ -n "$GITHUB_USERNAME" ]]; then
    # 使用 GHCR 镜像仓库
    REGISTRY="ghcr.io"
    REGISTRY_FULL="ghcr.io/${GITHUB_USERNAME}"
    USE_ACR=false
    log "使用 GHCR 镜像仓库: ${REGISTRY_FULL}"
    
    BACKEND_IMAGE="${REGISTRY_FULL}/knowhere-backend"
    FRONTEND_IMAGE="${REGISTRY_FULL}/knowhere-frontend"
    WORKER_IMAGE="${REGISTRY_FULL}/knowhere-worker"
else
    error "必须设置 ACR_REGISTRY 和 ACR_NAMESPACE，或设置 GITHUB_USERNAME"
fi

log "开始部署到 ECS 服务器: ${ECS_HOST}"
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
    
    ssh $SSH_OPTIONS -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} bash << EOF
        set -e
        
        # 设置变量（从外部传入）
        REGISTRY="${REGISTRY}"
        REGISTRY_FULL="${REGISTRY_FULL}"
        USE_ACR="${USE_ACR}"
        GITHUB_USERNAME="${GITHUB_USERNAME}"
        ALIYUN_ACR_USERNAME="${ALIYUN_ACR_USERNAME:-}"
        ALIYUN_ACR_PASSWORD="${ALIYUN_ACR_PASSWORD:-}"
        GITHUB_TOKEN="${GITHUB_TOKEN:-}"
        
        # 登录到镜像仓库
        if command -v docker &> /dev/null; then
            if [ "\$USE_ACR" = "true" ]; then
                # ACR 登录逻辑
                if [ -f ~/.docker/config.json ] && grep -q "\$REGISTRY" ~/.docker/config.json 2>/dev/null; then
                    echo "检测到已保存的 ACR 登录凭证，跳过登录"
                else
                    if [ -n "\$ALIYUN_ACR_USERNAME" ] && [ -n "\$ALIYUN_ACR_PASSWORD" ]; then
                        echo "\$ALIYUN_ACR_PASSWORD" | docker login --username="\$ALIYUN_ACR_USERNAME" --password-stdin "\$REGISTRY" 2>/dev/null || {
                            echo "警告: 无法使用环境变量登录到 ACR，尝试使用已保存的凭据"
                            docker login "\$REGISTRY" 2>/dev/null || {
                                echo "错误: 无法登录到 ACR，请先手动登录: docker login \$REGISTRY"
                                exit 1
                            }
                        }
                    else
                        echo "警告: 未设置 ACR 登录凭据，尝试使用已保存的凭据"
                        docker login "\$REGISTRY" 2>/dev/null || {
                            echo "错误: 无法登录到 ACR，请先手动登录: docker login \$REGISTRY"
                            exit 1
                        }
                    fi
                fi
            else
                # GHCR 登录逻辑
                if [ -f ~/.docker/config.json ] && grep -q "ghcr.io" ~/.docker/config.json 2>/dev/null; then
                    echo "检测到已保存的 GHCR 登录凭证，跳过登录"
                else
                    if [ -n "\$GITHUB_TOKEN" ]; then
                        echo "\$GITHUB_TOKEN" | docker login ghcr.io -u "\$GITHUB_USERNAME" --password-stdin 2>/dev/null || {
                            echo "警告: 无法使用 GITHUB_TOKEN 登录到 GHCR"
                        }
                    else
                        echo "警告: 未设置 GITHUB_TOKEN，尝试使用已保存的凭据"
                        docker login ghcr.io -u "\$GITHUB_USERNAME" 2>/dev/null || {
                            echo "警告: 无法登录到 GHCR，请确保服务器上已配置 GitHub token"
                            echo "可以在服务器上运行: echo \\\$GITHUB_TOKEN | docker login ghcr.io -u \$GITHUB_USERNAME --password-stdin"
                        }
                    fi
                fi
            fi
        else
            echo "错误: Docker 未安装"
            exit 1
        fi
        
        # 停止并删除旧容器
        docker stop ${CONTAINER_NAME} 2>/dev/null || true
        docker rm ${CONTAINER_NAME} 2>/dev/null || true
        
        # 拉取新镜像
        echo "拉取镜像: ${IMAGE_NAME}:${IMAGE_TAG}"
        if docker pull ${IMAGE_NAME}:${IMAGE_TAG} 2>&1; then
            IMAGE_TAG_ACTUAL="${IMAGE_TAG}"
            echo "成功拉取镜像: ${IMAGE_NAME}:${IMAGE_TAG}"
        else
            echo "警告: 无法拉取镜像 ${IMAGE_NAME}:${IMAGE_TAG}"
            # 尝试备用标签（根据环境推断）
            if [[ "${IMAGE_TAG}" == *"dev"* ]]; then
                FALLBACK_TAGS="dev-latest staging-latest latest"
            elif [[ "${IMAGE_TAG}" == *"staging"* ]]; then
                FALLBACK_TAGS="staging-latest dev-latest latest"
            elif [[ "${IMAGE_TAG}" == *"prod"* ]] || [[ "${IMAGE_TAG}" == *"main"* ]]; then
                FALLBACK_TAGS="main-latest prod-latest latest"
            else
                FALLBACK_TAGS="staging-latest dev-latest latest"
            fi
            
            PULL_SUCCESS=false
            for FALLBACK_TAG in \$FALLBACK_TAGS; do
                echo "尝试备用标签: ${IMAGE_NAME}:\$FALLBACK_TAG"
                if docker pull ${IMAGE_NAME}:\$FALLBACK_TAG 2>&1; then
                    IMAGE_TAG_ACTUAL="\$FALLBACK_TAG"
                    echo "成功拉取备用镜像: ${IMAGE_NAME}:\$FALLBACK_TAG"
                    PULL_SUCCESS=true
                    break
                fi
            done
            
            if [ "\$PULL_SUCCESS" != "true" ]; then
                echo "错误: 无法拉取镜像 ${IMAGE_NAME}，已尝试所有备用标签"
                exit 1
            fi
        fi
        
        # 运行新容器
        echo "启动容器: ${CONTAINER_NAME}"
        if docker run -d \\
            --name ${CONTAINER_NAME} \\
            --restart unless-stopped \\
            -p ${PORT}:${PORT} \\
            ${IMAGE_NAME}:\${IMAGE_TAG_ACTUAL:-${IMAGE_TAG}}; then
            echo "容器启动成功: ${CONTAINER_NAME}"
            
            # 等待容器启动
            sleep 2
            
            # 检查容器状态
            if docker ps | grep -q ${CONTAINER_NAME}; then
                echo "容器运行正常: ${CONTAINER_NAME}"
            else
                echo "警告: 容器 ${CONTAINER_NAME} 可能未正常运行，请检查日志"
                docker logs ${CONTAINER_NAME} --tail 20 2>/dev/null || true
            fi
        else
            echo "错误: 容器启动失败: ${CONTAINER_NAME}"
            exit 1
        fi
        
        # 清理未使用的镜像（保留最近使用的镜像）
        echo "清理未使用的镜像..."
        docker image prune -f --filter "until=24h" || true
        
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
log ""
log "后续操作:"
if [ -n "$SSH_OPTIONS" ]; then
    log "  检查服务状态: ssh $SSH_OPTIONS ${ECS_USER}@${ECS_HOST} 'docker ps'"
    log "  查看后端日志: ssh $SSH_OPTIONS ${ECS_USER}@${ECS_HOST} 'docker logs knowhere-backend --tail 50'"
    log "  查看前端日志: ssh $SSH_OPTIONS ${ECS_USER}@${ECS_HOST} 'docker logs knowhere-frontend --tail 50'"
else
    log "  检查服务状态: ssh ${ECS_USER}@${ECS_HOST} 'docker ps'"
    log "  查看后端日志: ssh ${ECS_USER}@${ECS_HOST} 'docker logs knowhere-backend --tail 50'"
    log "  查看前端日志: ssh ${ECS_USER}@${ECS_HOST} 'docker logs knowhere-frontend --tail 50'"
fi

