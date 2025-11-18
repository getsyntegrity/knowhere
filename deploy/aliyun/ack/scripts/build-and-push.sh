#!/bin/bash

# 构建和推送Docker镜像到阿里云容器镜像服务的脚本

set -e

# 配置变量
REGION=${REGION:-cn-shenzhen}
# 企业版容器镜像服务使用实例特定的endpoint
REGISTRY=${REGISTRY:-knowhere-registry.cn-shenzhen.cr.aliyuncs.com}
NAMESPACE=${NAMESPACE:-knowhere}
PROJECT_NAME=${PROJECT_NAME:-knowhere}
ACR_INSTANCE_ID=${ACR_INSTANCE_ID:-}  # 容器镜像服务企业版实例ID（可选，脚本会自动检测）
ENVIRONMENT=${ENVIRONMENT:-dev}  # dev/test/prod
BACKEND_IMAGE=${PROJECT_NAME}-backend
FRONTEND_IMAGE=${PROJECT_NAME}-frontend
WORKER_IMAGE=${PROJECT_NAME}-worker

# 版本管理 - 从Git Tag获取版本号
get_version() {
    # 尝试获取最新的Git Tag
    if git describe --tags --exact-match HEAD 2>/dev/null; then
        # 如果有精确匹配的Tag，使用Tag（保留v前缀）
        VERSION=$(git describe --tags --exact-match HEAD)
    elif git describe --tags HEAD 2>/dev/null; then
        # 如果有Tag（可能不是精确匹配），使用Tag和commit hash
        VERSION=$(git describe --tags HEAD)
        COMMIT=$(git rev-parse --short HEAD)
        VERSION="${VERSION}-${COMMIT}"
    else
        # 如果没有Tag，使用commit hash
        COMMIT=$(git rev-parse --short HEAD)
        VERSION="dev-${COMMIT}"
    fi
    echo "$VERSION"
}

APP_VERSION=${APP_VERSION:-$(get_version)}
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

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
    
    # 检查是否已经登录
    if [ -f ~/.docker/config.json ] && grep -q "$REGISTRY" ~/.docker/config.json 2>/dev/null; then
        log "检测到已保存的登录凭证，跳过登录"
        return 0
    fi
    
    # 优先使用阿里云 CLI 获取临时凭证（企业版需要实例ID）
    if command -v aliyun &> /dev/null; then
        log "尝试使用阿里云 CLI 获取临时凭证..."
        
        # 优先使用环境变量指定的实例ID
        if [ -n "$ACR_INSTANCE_ID" ]; then
            INSTANCE_ID="$ACR_INSTANCE_ID"
            log "使用环境变量指定的实例ID: $INSTANCE_ID"
        else
            # 检查是否有容器镜像服务实例
            INSTANCE_COUNT=$(aliyun cr GetInstanceCount --region ${REGION:-cn-shenzhen} 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin).get('Count', 0))" 2>/dev/null || echo "0")
            
            if [ "$INSTANCE_COUNT" != "0" ] && [ -n "$INSTANCE_COUNT" ]; then
                # 有企业版实例，获取实例 ID
                INSTANCE_INFO=$(aliyun cr ListInstance --region ${REGION:-cn-shenzhen} 2>/dev/null)
                if [ $? -eq 0 ] && [ -n "$INSTANCE_INFO" ]; then
                    # 尝试从列表获取第一个实例 ID
                    INSTANCE_ID=$(echo "$INSTANCE_INFO" | python3 -c "import sys, json; data=json.load(sys.stdin); instances=data.get('instances', []); print(instances[0].get('instanceId', '') if instances else '')" 2>/dev/null)
                fi
            fi
        fi
        
        # 如果找到了实例ID，尝试获取临时凭证
        if [ -n "$INSTANCE_ID" ]; then
            log "使用容器镜像服务实例: $INSTANCE_ID"
            TOKEN_INFO=$(aliyun cr GetAuthorizationToken --InstanceId "$INSTANCE_ID" --region ${REGION:-cn-shenzhen} 2>/dev/null)
            
            if [ $? -eq 0 ] && [ -n "$TOKEN_INFO" ]; then
                TEMP_USERNAME=$(echo "$TOKEN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tempUsername', ''))" 2>/dev/null)
                TEMP_PASSWORD=$(echo "$TOKEN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('authorizationToken', ''))" 2>/dev/null)
                
                if [ -n "$TEMP_USERNAME" ] && [ -n "$TEMP_PASSWORD" ]; then
                    log "使用临时凭证登录..."
                    LOGIN_OUTPUT=$(echo "$TEMP_PASSWORD" | docker login --username=$TEMP_USERNAME --password-stdin $REGISTRY 2>&1)
                    if [ $? -eq 0 ]; then
                        log "登录成功"
                        return 0
                    else
                        warn "临时凭证登录失败，错误信息: $LOGIN_OUTPUT"
                        warn "企业版可能需要使用阿里云账号直接登录，或配置实例访问控制"
                    fi
                fi
            else
                log "获取临时凭证失败，尝试其他方式"
            fi
        else
            log "未找到容器镜像服务实例（使用个人版或需要先创建实例）"
        fi
    fi
    
    # 回退到使用环境变量登录
    if [ -n "$ALIYUN_USERNAME" ] && [ -n "$ALIYUN_PASSWORD" ]; then
        log "使用环境变量登录..."
        echo "$ALIYUN_PASSWORD" | docker login --username=$ALIYUN_USERNAME --password-stdin $REGISTRY
        if [ $? -eq 0 ]; then
            return 0
        fi
    fi
    
    # 如果都失败，提示手动登录
    warn "无法自动登录，请先手动登录："
    warn "  docker login $REGISTRY"
    warn "然后重新运行此脚本"
    error "需要先登录到容器镜像服务"
}

# 构建和推送后端镜像
build_backend() {
    log "构建后端镜像 (环境: $ENVIRONMENT)..."
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $BACKEND_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.api \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        --build-arg APP_VERSION=$APP_VERSION \
        --build-arg BUILD_TIME=$BUILD_TIME \
        --build-arg GIT_COMMIT=$GIT_COMMIT \
        .
    
    # 标记镜像 - 使用版本号作为标签
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-latest
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$APP_VERSION
    docker tag $BACKEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送后端镜像到容器镜像服务..."
    log "版本号: $APP_VERSION"
    docker push $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-latest
    docker push $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$APP_VERSION
    docker push $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $BACKEND_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "后端镜像大小: $IMAGE_SIZE"
    log "后端镜像推送完成"
}

# 构建和推送前端镜像
build_frontend() {
    log "构建前端镜像 (环境: $ENVIRONMENT)..."
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $FRONTEND_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.web \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        --build-arg APP_VERSION=$APP_VERSION \
        --build-arg BUILD_TIME=$BUILD_TIME \
        --build-arg GIT_COMMIT=$GIT_COMMIT \
        .
    
    # 标记镜像 - 使用版本号作为标签
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-latest
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$APP_VERSION
    docker tag $FRONTEND_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送前端镜像到容器镜像服务..."
    log "版本号: $APP_VERSION"
    docker push $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-latest
    docker push $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$APP_VERSION
    docker push $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $FRONTEND_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "前端镜像大小: $IMAGE_SIZE"
    log "前端镜像推送完成"
}

# 构建和推送Worker镜像
build_worker() {
    log "构建Worker镜像 (环境: $ENVIRONMENT)..."
    
    # 构建镜像（从项目根目录，使用新的Dockerfile路径）
    docker build -t $WORKER_IMAGE:$ENVIRONMENT-latest \
        -f deploy/docker/Dockerfile.worker \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        --build-arg APP_VERSION=$APP_VERSION \
        --build-arg BUILD_TIME=$BUILD_TIME \
        --build-arg GIT_COMMIT=$GIT_COMMIT \
        .
    
    # 标记镜像 - 使用版本号作为标签
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-latest
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$APP_VERSION
    docker tag $WORKER_IMAGE:$ENVIRONMENT-latest $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 推送镜像
    log "推送Worker镜像到容器镜像服务..."
    log "版本号: $APP_VERSION"
    docker push $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-latest
    docker push $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$APP_VERSION
    docker push $REGISTRY/$NAMESPACE/$WORKER_IMAGE:$ENVIRONMENT-$GIT_COMMIT
    
    # 显示镜像大小
    IMAGE_SIZE=$(docker images $WORKER_IMAGE:$ENVIRONMENT-latest --format "{{.Size}}")
    log "Worker镜像大小: $IMAGE_SIZE"
    log "Worker镜像推送完成"
}

# 主函数
main() {
    log "开始构建和部署流程 (环境: $ENVIRONMENT)..."
    
    # 切换到项目根目录（脚本可能在子目录中运行）
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
    cd "$PROJECT_ROOT" || error "无法切换到项目根目录: $PROJECT_ROOT"
    log "工作目录: $(pwd)"
    
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

