#!/bin/bash

# Kubernetes部署脚本 - 阿里云ACK
# 使用环境变量替换Kubernetes配置文件中的占位符

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

# 检查环境变量
ENVIRONMENT=${ENVIRONMENT:-dev}
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    error "ENVIRONMENT must be one of: dev, test, prod"
fi

# 根据环境设置域名
case "$ENVIRONMENT" in
    dev)
        API_DOMAIN=${API_DOMAIN:-apidev.knowhereto.com}
        WEB_DOMAIN=${WEB_DOMAIN:-dev.knowhereto.com}
        API_URL=${API_URL:-https://apidev.knowhereto.com}
        ;;
    test)
        API_DOMAIN=${API_DOMAIN:-apitest.knowhereto.com}
        WEB_DOMAIN=${WEB_DOMAIN:-test.knowhereto.com}
        API_URL=${API_URL:-https://apitest.knowhereto.com}
        ;;
    prod)
        API_DOMAIN=${API_DOMAIN:-api.knowhereto.com}
        WEB_DOMAIN=${WEB_DOMAIN:-knowhereto.com}
        API_URL=${API_URL:-https://api.knowhereto.com}
        ;;
esac

# 默认值
REGISTRY=${REGISTRY:-registry.cn-shenzhen.aliyuncs.com}
NAMESPACE=${NAMESPACE:-knowhere}
API_REPLICAS=${API_REPLICAS:-2}
WEB_REPLICAS=${WEB_REPLICAS:-2}
WORKER_REPLICAS=${WORKER_REPLICAS:-1}
APP_VERSION=${APP_VERSION:-$(git describe --tags --exact-match HEAD 2>/dev/null || echo "${ENVIRONMENT}-$(git rev-parse --short HEAD)")}
OSS_BUCKET_NAME=${OSS_BUCKET_NAME:-}

log "部署环境: $ENVIRONMENT"
log "API域名: $API_DOMAIN"
log "Web域名: $WEB_DOMAIN"
log "API URL: $API_URL"
log "应用版本: $APP_VERSION"

# 检查必要的工具
if ! command -v kubectl &> /dev/null; then
    error "kubectl 未安装，请先安装 kubectl"
fi

if ! command -v envsubst &> /dev/null; then
    error "envsubst 未安装，请先安装 gettext 包"
fi

# 检查kubeconfig
if ! kubectl cluster-info &> /dev/null; then
    error "无法连接到Kubernetes集群，请检查kubeconfig配置"
fi

# 导出环境变量供envsubst使用
export ENVIRONMENT
export REGISTRY
export NAMESPACE
export API_DOMAIN
export WEB_DOMAIN
export API_URL
export API_REPLICAS
export WEB_REPLICAS
export WORKER_REPLICAS
export APP_VERSION
export OSS_BUCKET_NAME

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_BASE_DIR="$SCRIPT_DIR/../kubernetes/base"
K8S_ENV_DIR="$SCRIPT_DIR/../kubernetes/$ENVIRONMENT"
TEMP_DIR=$(mktemp -d)

# 清理函数
cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

log "开始部署Kubernetes资源..."

# 处理基础配置文件
for file in "$K8S_BASE_DIR"/*.yaml; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        log "处理文件: $filename"
        envsubst < "$file" > "$TEMP_DIR/$filename"
    fi
done

# 应用命名空间
log "创建命名空间..."
kubectl apply -f "$TEMP_DIR/namespace.yaml" || true

# 应用ConfigMap
log "创建ConfigMap..."
kubectl apply -f "$TEMP_DIR/configmap.yaml"

# 应用Secrets（如果存在）
if [ -f "$TEMP_DIR/secrets.yaml" ]; then
    warn "检测到secrets.yaml文件，请确保已正确设置所有敏感值"
    log "应用Secrets..."
    kubectl apply -f "$TEMP_DIR/secrets.yaml"
fi

# 应用PVC（如果存在）
if [ -f "$TEMP_DIR/pvc-model-cache.yaml" ]; then
    log "创建PVC..."
    kubectl apply -f "$TEMP_DIR/pvc-model-cache.yaml"
fi

# 应用Service
log "创建Service..."
kubectl apply -f "$TEMP_DIR/service.yaml"

# 应用Deployment
log "创建Deployment..."
kubectl apply -f "$TEMP_DIR/deployment-api.yaml"
kubectl apply -f "$TEMP_DIR/deployment-web.yaml"
if [ -f "$TEMP_DIR/deployment-worker.yaml" ]; then
    kubectl apply -f "$TEMP_DIR/deployment-worker.yaml"
fi

# 应用Ingress
log "创建Ingress..."
kubectl apply -f "$TEMP_DIR/ingress.yaml"

log "部署完成！"
log ""
log "验证部署状态："
kubectl get pods -n "$NAMESPACE"
kubectl get ingress -n "$NAMESPACE"

