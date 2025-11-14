#!/bin/bash

# 构建和推送Docker镜像到阿里云容器镜像服务的脚本

set -e

# 配置变量
REGION=${REGION:-cn-hangzhou}
REGISTRY=${REGISTRY:-registry.cn-hangzhou.aliyuncs.com}
NAMESPACE=${NAMESPACE:-knowhere}
PROJECT_NAME=${PROJECT_NAME:-knowhere}
ENVIRONMENT=${ENVIRONMENT:-dev}  # dev/test/prod
BACKEND_IMAGE=${PROJECT_NAME}-backend
FRONTEND_IMAGE=${PROJECT_NAME}-frontend
WORKER_IMAGE=${PROJECT_NAME}-worker

# 验证环境参数
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    echo "ERROR: ENVIRONMENT must be one of: dev, test, prod"
    exit 1
fi

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
check_requirements() {
    log "检查环境变量..."
    
    if [ -z "$REGISTRY" ]; then
        error "REGISTRY 环境变量未设置"
    fi
    
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装"
    fi
    
    log "环境检查通过"
}

# 登录容器镜像服务
login_registry() {
    log "登录到阿里云容器镜像服务..."
    docker login --username=$ALIYUN_USERNAME --password=$ALIYUN_PASSWORD $REGISTRY
}

# 构建和推送后端镜像
build_backend() {
    log "构建后端镜像 (环境: $ENVIRONMENT)..."
    
    # 获取Git commit hash
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $BACKEND_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.api \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        .
    
    # 标记镜像
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-latest
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送后端镜像到容器镜像服务..."
    docker push $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-latest
    docker push $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $BACKEND_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "后端镜像大小: $IMAGE_SIZE"
    log "后端镜像推送完成"
}

# 构建和推送前端镜像
build_frontend() {
    log "构建前端镜像 (环境: $ENVIRONMENT)..."
    
    # 获取Git commit hash
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $FRONTEND_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.web \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        .
    
    # 标记镜像
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-latest
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送前端镜像到容器镜像服务..."
    docker push $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-latest
    docker push $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $FRONTEND_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "前端镜像大小: $IMAGE_SIZE"
    log "前端镜像推送完成"
}

# 构建和推送Worker镜像
build_worker() {
    log "构建Worker镜像 (环境: $ENVIRONMENT)..."
    
    # 获取Git commit hash
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $WORKER_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.worker \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        .
    
    # 标记镜像
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-latest
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送Worker镜像到容器镜像服务..."
    docker push $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-latest
    docker push $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $WORKER_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "Worker镜像大小: $IMAGE_SIZE"
    log "Worker镜像推送完成"
}

# 主函数
main() {
    log "开始构建和部署流程 (环境: $ENVIRONMENT)..."
    
    check_requirements
    login_registry
    build_backend
    build_frontend
    build_worker
    
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    log "构建和推送完成！"
    log "后端镜像: $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-latest"
    log "前端镜像: $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-latest"
    log "Worker镜像: $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-latest"
    log ""
    log "使用环境变量 ENVIRONMENT=dev|test|prod 来指定环境"
}

# 运行主函数
main "$@"

