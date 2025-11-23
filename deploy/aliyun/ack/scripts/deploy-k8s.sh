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

# 环境配置（仅支持prod）
ENV_TYPE=${ENVIRONMENT:-prod}
if [ "$ENV_TYPE" != "prod" ]; then
    error "仅支持 prod 环境部署"
fi

# 设置ENVIRONMENT为production（应用期望的值），DEBUG等配置变量
export ENVIRONMENT=production
export DEBUG=${DEBUG:-false}
export LOG_LEVEL=${LOG_LEVEL:-INFO}

# 生产环境域名配置
        API_DOMAIN=${API_DOMAIN:-api.knowhereto.com}
        WEB_DOMAIN=${WEB_DOMAIN:-knowhereto.com}
        API_URL=${API_URL:-https://api.knowhereto.com}

# SLB 实例 ID 配置
API_SLB_ID=${API_SLB_ID:-}
WEB_SLB_ID=${WEB_SLB_ID:-}

# 默认值
ACR_REGISTRY=${ACR_REGISTRY:-}
ACR_NAMESPACE=${ACR_NAMESPACE:-knowhere}
NAMESPACE=${NAMESPACE:-knowhere}
API_REPLICAS=${API_REPLICAS:-2}
WEB_REPLICAS=${WEB_REPLICAS:-2}
WORKER_REPLICAS=${WORKER_REPLICAS:-1}
APP_VERSION=${APP_VERSION:-$(git describe --tags --exact-match HEAD 2>/dev/null || echo "prod-$(git rev-parse --short HEAD)")}
OSS_BUCKET_NAME=${OSS_BUCKET_NAME:-}

# 部署服务配置：支持 api,web,worker，用逗号分隔，默认全部部署
DEPLOY_SERVICES=${DEPLOY_SERVICES:-api,web,worker}
DEPLOY_API=false
DEPLOY_WEB=false
DEPLOY_WORKER=false

# 解析要部署的服务
IFS=',' read -ra SERVICES <<< "$DEPLOY_SERVICES"
for service in "${SERVICES[@]}"; do
    # 转换为小写（兼容不同bash版本）
    service_lower=$(echo "$service" | tr '[:upper:]' '[:lower:]')
    case "$service_lower" in
        api)
            DEPLOY_API=true
            ;;
        web)
            DEPLOY_WEB=true
            ;;
        worker)
            DEPLOY_WORKER=true
            ;;
        *)
            warn "未知的服务类型: $service，将被忽略"
            ;;
    esac
done

# 镜像标签：prod 环境使用 main-latest
IMAGE_TAG=${IMAGE_TAG:-main-latest}

# 镜像仓库配置：仅使用 ACR（阿里云容器镜像服务）
if [[ -n "$ACR_REGISTRY" ]]; then
    # 使用指定的 ACR 镜像仓库
    REGISTRY="$ACR_REGISTRY/$ACR_NAMESPACE"
    log "使用 ACR 镜像仓库: $REGISTRY"
else
    # 使用默认 ACR 配置（深圳仓库）
    REGISTRY="knowhere-registry.cn-shenzhen.cr.aliyuncs.com/$ACR_NAMESPACE"
    log "使用默认 ACR 镜像仓库: $REGISTRY"
fi

    # 检查是否存在 acr-secret
    if kubectl get secret acr-secret -n "$NAMESPACE" &>/dev/null; then
        IMAGE_PULL_SECRETS="imagePullSecrets:
      - name: acr-secret"
        log "检测到 acr-secret，将使用私有镜像仓库认证"
    else
    warn "未找到 acr-secret，镜像拉取可能失败"
    warn "请确保已创建 acr-secret: kubectl create secret docker-registry acr-secret --docker-server=\$ACR_REGISTRY --docker-username=\$ACR_USERNAME --docker-password=\$ACR_PASSWORD -n $NAMESPACE"
        IMAGE_PULL_SECRETS=""
fi

log "部署环境: $ENVIRONMENT"
log "镜像仓库: $REGISTRY"
log "API域名: $API_DOMAIN"
log "Web域名: $WEB_DOMAIN"
log "API URL: $API_URL"
log "应用版本: $APP_VERSION"
log "部署服务: $DEPLOY_SERVICES"
log "  - API: $DEPLOY_API"
log "  - Web: $DEPLOY_WEB"
log "  - Worker: $DEPLOY_WORKER"

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

# 设置ConfigMap需要的环境变量默认值
export DEBUG=${DEBUG:-false}
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export APP_TITLE=${APP_TITLE:-Konwhere AI知识库管理系统}
export APP_DESCRIPTION=${APP_DESCRIPTION:-基于AI的知识库管理和智能问答系统}
export TMP_PATH=${TMP_PATH:-/tmp/aismart_bid}
export FONT_PATH=${FONT_PATH:-/usr/share/fonts}
export CHROMEDRIVER_PATH=${CHROMEDRIVER_PATH:-/usr/bin/chromedriver}
export USERS_DATA_PATH=${USERS_DATA_PATH:-/app/users}
export ALGORITHM=${ALGORITHM:-HS256}
export ACCESS_TOKEN_EXPIRE_MINUTES=${ACCESS_TOKEN_EXPIRE_MINUTES:-10080}
export DB_SSL_MODE=${DB_SSL_MODE:-disable}
export REDIS_DATABASE=${REDIS_DATABASE:-0}
export RABBITMQ_PORT=${RABBITMQ_PORT:-5672}
export RABBITMQ_VHOST=${RABBITMQ_VHOST:-/}
export MESSAGE_BROKER_TYPE=${MESSAGE_BROKER_TYPE:-rabbitmq}
export CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND:-rpc://}
export S3_TYPE=${S3_TYPE:-oss}
export S3_TEMP_PATH=${S3_TEMP_PATH:-/tmp}
export SUPPORTED_EXTENSIONS=${SUPPORTED_EXTENSIONS:-.doc,.docx,.pdf,.txt,.xls,.xlsx,.csv,.jpg,.png}
export MAX_FILE_SIZE=${MAX_FILE_SIZE:-104857600}
export MAX_IMAGE_SIZE=${MAX_IMAGE_SIZE:-10485760}
export MIN_CONFIDENCE_THRESHOLD=${MIN_CONFIDENCE_THRESHOLD:-0.05}
export HIGH_IOU_THRESHOLD=${HIGH_IOU_THRESHOLD:-0.9}
export DEFAULT_EMBEDDING_DIM=${DEFAULT_EMBEDDING_DIM:-1024}
export DEFAULT_TOP_K=${DEFAULT_TOP_K:-5}
export DEFAULT_BATCH_SIZE=${DEFAULT_BATCH_SIZE:-32}
export DEFAULT_EPOCHS=${DEFAULT_EPOCHS:-3}
export DEFAULT_THRESHOLD=${DEFAULT_THRESHOLD:-0.5}
export SMTP_HOST=${SMTP_HOST:-smtp.gmail.com}
export SMTP_PORT=${SMTP_PORT:-587}
export EMAILS_FROM_NAME=${EMAILS_FROM_NAME:-AI Smart Bid}
export DS_URL=${DS_URL:-https://api.deepseek.com/v1/chat/completions}
export ALI_URL=${ALI_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}
export ARK_URL=${ARK_URL:-https://ark.cn-beijing.volces.com/api/v3/chat/completions}
export EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-v1}
export NORMAL_MODEL=${NORMAL_MODEL:-gpt-3.5-turbo}
export IMAGE_MODEL=${IMAGE_MODEL:-gpt-4-vision-preview}
export MINERU_URL=${MINERU_URL:-https://mineru.net/api/v4/extract/task}

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
export IMAGE_PULL_SECRETS
export IMAGE_TAG
export API_SLB_ID
export WEB_SLB_ID

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_BASE_DIR="$SCRIPT_DIR/../kubernetes/base"
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

# 应用Secrets（如果存在且Secret不存在）
if [ -f "$TEMP_DIR/secrets.yaml" ]; then
    if kubectl get secret knowhere-secrets -n "$NAMESPACE" &>/dev/null; then
        log "Secret 'knowhere-secrets' 已存在，跳过应用 secrets.yaml"
    else
        warn "检测到secrets.yaml文件，请确保已正确设置所有敏感值"
        log "应用Secrets..."
        kubectl apply -f "$TEMP_DIR/secrets.yaml"
    fi
fi

# 应用PVC（如果存在，失败时继续）
if [ -f "$TEMP_DIR/pvc-model-cache.yaml" ]; then
    log "创建PVC..."
    if kubectl apply -f "$TEMP_DIR/pvc-model-cache.yaml" 2>&1; then
        log "PVC 创建成功"
    else
        warn "PVC 创建失败，继续部署其他资源（Worker 服务可能需要 PVC）"
    fi
fi

# 生成Service配置（只包含需要部署的服务）
log "生成Service配置..."
SERVICE_FILE="$TEMP_DIR/service-filtered.yaml"
> "$SERVICE_FILE"  # 清空文件

if [ "$DEPLOY_API" = true ]; then
    log "  包含 API Service"
    if [ -n "$API_SLB_ID" ]; then
        log "  使用 LoadBalancer 类型，关联 SLB: $API_SLB_ID"
        cat >> "$SERVICE_FILE" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: knowhere-api
  namespace: ${NAMESPACE}
  labels:
    app: knowhere-api
  annotations:
    service.beta.kubernetes.io/alibaba-cloud-loadbalancer-id: "${API_SLB_ID}"
    service.beta.kubernetes.io/alibaba-cloud-loadbalancer-force-override-listeners: "false"
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 5005
    protocol: TCP
    name: http
  - port: 443
    targetPort: 5005
    protocol: TCP
    name: https
  selector:
    app: knowhere-api
EOF
    else
        log "  使用 ClusterIP 类型（未配置 API_SLB_ID）"
    cat >> "$SERVICE_FILE" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: knowhere-api
  namespace: ${NAMESPACE}
  labels:
    app: knowhere-api
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 5005
    protocol: TCP
    name: http
  selector:
    app: knowhere-api
EOF
    fi
    if [ "$DEPLOY_WEB" = true ] || [ "$DEPLOY_WORKER" = true ]; then
        echo "---" >> "$SERVICE_FILE"
    fi
fi

if [ "$DEPLOY_WEB" = true ]; then
    log "  包含 Web Service"
    if [ -n "$WEB_SLB_ID" ]; then
        log "  使用 LoadBalancer 类型，关联 SLB: $WEB_SLB_ID"
        cat >> "$SERVICE_FILE" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: knowhere-web
  namespace: ${NAMESPACE}
  labels:
    app: knowhere-web
  annotations:
    service.beta.kubernetes.io/alibaba-cloud-loadbalancer-id: "${WEB_SLB_ID}"
    service.beta.kubernetes.io/alibaba-cloud-loadbalancer-force-override-listeners: "false"
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 3000
    protocol: TCP
    name: http
  - port: 443
    targetPort: 3000
    protocol: TCP
    name: https
  selector:
    app: knowhere-web
EOF
    else
        log "  使用 ClusterIP 类型（未配置 WEB_SLB_ID）"
    cat >> "$SERVICE_FILE" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: knowhere-web
  namespace: ${NAMESPACE}
  labels:
    app: knowhere-web
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 3000
    protocol: TCP
    name: http
  selector:
    app: knowhere-web
EOF
    fi
    if [ "$DEPLOY_WORKER" = true ]; then
        echo "---" >> "$SERVICE_FILE"
    fi
fi

if [ "$DEPLOY_WORKER" = true ]; then
    log "  包含 Worker Service"
    cat >> "$SERVICE_FILE" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: knowhere-worker
  namespace: ${NAMESPACE}
  labels:
    app: knowhere-worker
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
    name: http
  selector:
    app: knowhere-worker
EOF
fi

# 应用Service
log "创建Service..."
kubectl apply -f "$SERVICE_FILE"

# 应用Deployment
log "创建Deployment..."
if [ "$DEPLOY_API" = true ]; then
    log "  部署 API Deployment"
kubectl apply -f "$TEMP_DIR/deployment-api.yaml"
fi

if [ "$DEPLOY_WEB" = true ]; then
    log "  部署 Web Deployment"
kubectl apply -f "$TEMP_DIR/deployment-web.yaml"
fi

if [ "$DEPLOY_WORKER" = true ]; then
if [ -f "$TEMP_DIR/deployment-worker.yaml" ]; then
        log "  部署 Worker Deployment"
    kubectl apply -f "$TEMP_DIR/deployment-worker.yaml"
    else
        warn "  deployment-worker.yaml 不存在，跳过 Worker 部署"
    fi
fi

# 生成Ingress配置（只包含需要部署的服务）
log "生成Ingress配置..."
INGRESS_FILE="$TEMP_DIR/ingress-filtered.yaml"
> "$INGRESS_FILE"  # 清空文件

cat >> "$INGRESS_FILE" <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: knowhere-ingress
  namespace: ${NAMESPACE}
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
spec:
  tls:
  - hosts:
EOF

# 添加TLS hosts
if [ "$DEPLOY_API" = true ]; then
    echo "    - ${API_DOMAIN}" >> "$INGRESS_FILE"
fi
if [ "$DEPLOY_WEB" = true ]; then
    echo "    - ${WEB_DOMAIN}" >> "$INGRESS_FILE"
fi

cat >> "$INGRESS_FILE" <<EOF
    secretName: knowhere-tls
  rules:
EOF

# 添加API规则
if [ "$DEPLOY_API" = true ]; then
    cat >> "$INGRESS_FILE" <<EOF
  - host: ${API_DOMAIN}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: knowhere-api
            port:
              number: 80
EOF
fi

# 添加Web规则
if [ "$DEPLOY_WEB" = true ]; then
    if [ "$DEPLOY_API" = true ]; then
        echo "" >> "$INGRESS_FILE"
    fi
    cat >> "$INGRESS_FILE" <<EOF
  - host: ${WEB_DOMAIN}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: knowhere-web
            port:
              number: 80
EOF
fi

# 应用Ingress
log "创建Ingress..."
kubectl apply -f "$INGRESS_FILE"

log "部署完成！"
log ""
log "验证部署状态："
kubectl get pods -n "$NAMESPACE"
kubectl get ingress -n "$NAMESPACE"

