#!/bin/bash

# 构建和推送Docker镜像到ECR的脚本

set -e

# 配置变量
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
PROJECT_NAME=${PROJECT_NAME:-knowhere}
ENVIRONMENT=${ENVIRONMENT:-dev}  # dev/test/prod
BACKEND_IMAGE=${PROJECT_NAME}-backend
FRONTEND_IMAGE=${PROJECT_NAME}-frontend
WORKER_IMAGE=${PROJECT_NAME}-worker

# 验证环境参数
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    error "ENVIRONMENT must be one of: dev, test, prod"
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
    
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        error "AWS_ACCOUNT_ID 环境变量未设置"
    fi
    
    if ! command -v aws &> /dev/null; then
        error "AWS CLI 未安装"
    fi
    
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装"
    fi
    
    log "环境检查通过"
}

# 登录ECR
login_ecr() {
    log "登录到ECR..."
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
}

# 构建和推送后端镜像
build_backend() {
    log "构建后端镜像 (环境: $ENVIRONMENT)..."
    
    # 检查ECR仓库是否存在
    if ! aws ecr describe-repositories --repository-names $BACKEND_IMAGE --region $AWS_REGION &> /dev/null; then
        warn "ECR仓库 $BACKEND_IMAGE 不存在，正在创建..."
        aws ecr create-repository --repository-name $BACKEND_IMAGE --region $AWS_REGION
    fi
    
    # 获取Git commit hash
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $BACKEND_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.api \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        .
    
    # 标记镜像
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$BACKEND_IMAGE:$ENVIRONMENT-latest
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$BACKEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送后端镜像到ECR..."
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$BACKEND_IMAGE:$ENVIRONMENT-latest
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$BACKEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $BACKEND_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "后端镜像大小: $IMAGE_SIZE"
    log "后端镜像推送完成"
}

# 构建和推送前端镜像
build_frontend() {
    log "构建前端镜像 (环境: $ENVIRONMENT)..."
    
    # 检查ECR仓库是否存在
    if ! aws ecr describe-repositories --repository-names $FRONTEND_IMAGE --region $AWS_REGION &> /dev/null; then
        warn "ECR仓库 $FRONTEND_IMAGE 不存在，正在创建..."
        aws ecr create-repository --repository-name $FRONTEND_IMAGE --region $AWS_REGION
    fi
    
    # 获取Git commit hash
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $FRONTEND_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.web \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        .
    
    # 标记镜像
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$FRONTEND_IMAGE:$ENVIRONMENT-latest
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$FRONTEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送前端镜像到ECR..."
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$FRONTEND_IMAGE:$ENVIRONMENT-latest
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$FRONTEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $FRONTEND_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "前端镜像大小: $IMAGE_SIZE"
    log "前端镜像推送完成"
}

# 构建和推送Worker镜像
build_worker() {
    log "构建Worker镜像 (环境: $ENVIRONMENT)..."
    
    # 检查ECR仓库是否存在
    if ! aws ecr describe-repositories --repository-names $WORKER_IMAGE --region $AWS_REGION &> /dev/null; then
        warn "ECR仓库 $WORKER_IMAGE 不存在，正在创建..."
        aws ecr create-repository --repository-name $WORKER_IMAGE --region $AWS_REGION
    fi
    
    # 获取Git commit hash
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $WORKER_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.worker \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        .
    
    # 标记镜像
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$WORKER_IMAGE:$ENVIRONMENT-latest
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$WORKER_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送Worker镜像到ECR..."
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$WORKER_IMAGE:$ENVIRONMENT-latest
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$WORKER_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $WORKER_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "Worker镜像大小: $IMAGE_SIZE"
    log "Worker镜像推送完成"
}

# 更新ECS服务
update_ecs_services() {
    log "更新ECS服务 (环境: $ENVIRONMENT)..."
    
    CLUSTER_NAME="${PROJECT_NAME}-${ENVIRONMENT}-cluster"
    
    # 更新后端服务
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $PROJECT_NAME-$ENVIRONMENT-backend-service \
        --force-new-deployment \
        --region $AWS_REGION
    
    # 更新前端服务
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $PROJECT_NAME-$ENVIRONMENT-frontend-service \
        --force-new-deployment \
        --region $AWS_REGION
    
    # 更新Worker服务
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $PROJECT_NAME-$ENVIRONMENT-worker-service \
        --force-new-deployment \
        --region $AWS_REGION
    
    log "ECS服务更新完成"
}

# 主函数
main() {
    log "开始构建和部署流程 (环境: $ENVIRONMENT)..."
    
    check_requirements
    login_ecr
    build_backend
    build_frontend
    build_worker
    
    if [ "$1" = "--deploy" ]; then
        update_ecs_services
    fi
    
    GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    log "构建和推送完成！"
    log "后端镜像: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$BACKEND_IMAGE:$ENVIRONMENT-latest"
    log "前端镜像: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$FRONTEND_IMAGE:$ENVIRONMENT-latest"
    log "Worker镜像: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$WORKER_IMAGE:$ENVIRONMENT-latest"
    log ""
    log "使用环境变量 ENVIRONMENT=dev|test|prod 来指定环境"
}

# 运行主函数
main "$@"
