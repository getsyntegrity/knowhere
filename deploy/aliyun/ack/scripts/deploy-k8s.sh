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

# SLB 实例 ID 配置（使用当前实际存在的SLB）
# 注意：这些是Kubernetes自动创建的SLB ID，已保存用于后续部署
API_SLB_ID=${API_SLB_ID:-lb-7xvpdva6f4faiy8w85ar0}
WEB_SLB_ID=${WEB_SLB_ID:-lb-7xvj9rjc1ehi50z6vlqlc}

# SSL 证书配置（用于 HTTPS）
# 阿里云证书 ID: 1872946667951752_19ab0485602_935740748_-1131298329
SSL_CERT_ID=${SSL_CERT_ID:-1872946667951752_19ab0485602_935740748_-1131298329}
# 或者使用本地证书文件（如果设置了，将优先使用）
SSL_CERT_FILE=${SSL_CERT_FILE:-}
SSL_KEY_FILE=${SSL_KEY_FILE:-}

# 验证 SLB ID 配置
if [ "$DEPLOY_API" = true ] || [ "$DEPLOY_WEB" = true ]; then
    # 如果指定了SLB ID，检查两个 SLB ID 是否相同
    if [ -n "$API_SLB_ID" ] && [ -n "$WEB_SLB_ID" ] && [ "$API_SLB_ID" = "$WEB_SLB_ID" ]; then
        error "API_SLB_ID 和 WEB_SLB_ID 不能相同！请为每个服务配置不同的 SLB 实例。"
    fi
    # 如果未指定SLB ID，Kubernetes将自动创建新的SLB
    if [ "$DEPLOY_API" = true ] && [ -z "$API_SLB_ID" ]; then
        log "API_SLB_ID 未设置，Kubernetes将自动创建新的SLB"
    fi
    if [ "$DEPLOY_WEB" = true ] && [ -z "$WEB_SLB_ID" ]; then
        log "WEB_SLB_ID 未设置，Kubernetes将自动创建新的SLB"
    fi
fi

# 默认值
ACR_REGISTRY=${ACR_REGISTRY:-}
ACR_NAMESPACE=${ACR_NAMESPACE:-knowhere}
NAMESPACE=${NAMESPACE:-knowhere}
API_REPLICAS=${API_REPLICAS:-2}
WEB_REPLICAS=${WEB_REPLICAS:-2}
WORKER_REPLICAS=${WORKER_REPLICAS:-2}
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
log "  - API: $DEPLOY_API (SLB: $API_SLB_ID)"
log "  - Web: $DEPLOY_WEB (SLB: $WEB_SLB_ID)"
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
export APP_VERSION=${APP_VERSION:-$(git describe --tags --exact-match HEAD 2>/dev/null || echo "prod-$(git rev-parse --short HEAD)")}
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
# 修复：统一使用 S3_BUCKET_NAME，如果 OSS_BUCKET_NAME 存在则使用它
export S3_BUCKET_NAME=${S3_BUCKET_NAME:-${OSS_BUCKET_NAME:-knowhere-dev-storage-tcn1rvuu}}
export S3_TEMP_PATH=${S3_TEMP_PATH:-/tmp}
export OSS_ENDPOINT=${OSS_ENDPOINT:-https://oss-cn-guangzhou.aliyuncs.com}
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
export SMTP_USER=${SMTP_USER:-}
export EMAILS_FROM_EMAIL=${EMAILS_FROM_EMAIL:-}
export EMAILS_FROM_NAME=${EMAILS_FROM_NAME:-AI Smart Bid}
export DS_URL=${DS_URL:-https://api.deepseek.com/v1/chat/completions}
export ALI_URL=${ALI_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}
export ARK_URL=${ARK_URL:-https://ark.cn-beijing.volces.com/api/v3/chat/completions}
export EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-v1}
export NORMAL_MODEL=${NORMAL_MODEL:-gpt-3.5-turbo}
export IMAGE_MODEL=${IMAGE_MODEL:-qwen-vl-plus}
export IMAGE_MODEL_MAX=${IMAGE_MODEL_MAX:-qwen-vl-max}
export MINERU_URL=${MINERU_URL:-https://mineru.net/api/v4/extract/task}

# OAuth和支付配置（可选，默认为空）
export USERS_VERIFY_TOKEN_SECRET=${USERS_VERIFY_TOKEN_SECRET:-}
export USERS_RESET_PASSWORD_TOKEN_SECRET=${USERS_RESET_PASSWORD_TOKEN_SECRET:-}
export STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY:-}
export STRIPE_PUBLISHABLE_KEY=${STRIPE_PUBLISHABLE_KEY:-}
export STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET:-}
export GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}
export GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET:-}
export GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID:-}
export GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET:-}
export APPLE_CLIENT_ID=${APPLE_CLIENT_ID:-}
export APPLE_CLIENT_SECRET=${APPLE_CLIENT_SECRET:-}
export SMTP_PASSWORD=${SMTP_PASSWORD:-}

# 导出所有环境变量供envsubst使用（确保所有ConfigMap需要的变量都被导出）
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
export S3_BUCKET_NAME
export IMAGE_PULL_SECRETS
export IMAGE_TAG
export API_SLB_ID
export WEB_SLB_ID
export API_SSL_CERT_ID
export WEB_SSL_CERT_ID

# 导出所有ConfigMap需要的环境变量
export DEBUG
export LOG_LEVEL
export APP_TITLE
export APP_DESCRIPTION
export TMP_PATH
export FONT_PATH
export CHROMEDRIVER_PATH
export USERS_DATA_PATH
export ALGORITHM
export ACCESS_TOKEN_EXPIRE_MINUTES
export DB_SSL_MODE
export REDIS_DATABASE
export RABBITMQ_PORT
export RABBITMQ_VHOST
export MESSAGE_BROKER_TYPE
export CELERY_RESULT_BACKEND
export S3_TYPE
export S3_TEMP_PATH
export OSS_ENDPOINT
export SUPPORTED_EXTENSIONS
export MAX_FILE_SIZE
export MAX_IMAGE_SIZE
export MIN_CONFIDENCE_THRESHOLD
export HIGH_IOU_THRESHOLD
export DEFAULT_EMBEDDING_DIM
export DEFAULT_TOP_K
export DEFAULT_BATCH_SIZE
export DEFAULT_EPOCHS
export DEFAULT_THRESHOLD
export SMTP_HOST
export SMTP_PORT
export SMTP_USER
export EMAILS_FROM_EMAIL
export EMAILS_FROM_NAME
export DS_URL
export ALI_URL
export ARK_URL
export EMBEDDING_MODEL
export NORMAL_MODEL
export IMAGE_MODEL
export IMAGE_MODEL_MAX
export MINERU_URL
export USERS_VERIFY_TOKEN_SECRET
export USERS_RESET_PASSWORD_TOKEN_SECRET
export STRIPE_SECRET_KEY
export STRIPE_PUBLISHABLE_KEY
export STRIPE_WEBHOOK_SECRET
export GOOGLE_CLIENT_ID
export GOOGLE_CLIENT_SECRET
export GITHUB_CLIENT_ID
export GITHUB_CLIENT_SECRET
export APPLE_CLIENT_ID
export APPLE_CLIENT_SECRET
export SMTP_PASSWORD

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
        
        # 验证：检查是否还有未替换的占位符（除了secrets.yaml，因为它可能包含base64编码的值）
        if [ "$filename" != "secrets.yaml" ]; then
            if grep -q '\${[A-Z_]*}' "$TEMP_DIR/$filename" 2>/dev/null; then
                warn "文件 $filename 中检测到未替换的占位符："
                grep -o '\${[A-Z_]*}' "$TEMP_DIR/$filename" | sort -u | while read -r placeholder; do
                    warn "  - $placeholder"
                done
            fi
        fi
    fi
done

# 应用命名空间
log "创建命名空间..."
kubectl apply -f "$TEMP_DIR/namespace.yaml" || true

# 应用ConfigMap
log "创建ConfigMap..."
kubectl apply -f "$TEMP_DIR/configmap.yaml"

# 验证ConfigMap内容
log "验证ConfigMap内容..."
if kubectl get configmap knowhere-config -n "$NAMESPACE" &>/dev/null; then
    # 检查ConfigMap中是否还有占位符
    configmap_data=$(kubectl get configmap knowhere-config -n "$NAMESPACE" -o yaml)
    if echo "$configmap_data" | grep -q '\${[A-Z_]*}'; then
        warn "ConfigMap中检测到未替换的占位符，请检查环境变量配置"
        echo "$configmap_data" | grep -o '\${[A-Z_]*}' | sort -u | while read -r placeholder; do
            warn "  - $placeholder"
        done
    else
        log "ConfigMap验证通过，所有占位符已正确替换"
    fi
fi

# 应用Secrets（如果存在且Secret不存在）
if [ -f "$TEMP_DIR/secrets.yaml" ]; then
    if kubectl get secret knowhere-secrets -n "$NAMESPACE" &>/dev/null; then
        log "Secret 'knowhere-secrets' 已存在，跳过应用 secrets.yaml"
        warn "如需更新Secret，请手动更新或删除现有Secret后重新部署"
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

# 使用base/service.yaml文件（已配置为ClusterIP类型，使用Ingress统一入口）
log "使用Service配置（ClusterIP类型，通过Ingress统一入口）..."
SERVICE_FILE="$TEMP_DIR/service.yaml"
envsubst < "$K8S_BASE_DIR/service.yaml" > "$SERVICE_FILE"

log "  包含的服务:"
[ "$DEPLOY_API" = true ] && log "    - API Service (ClusterIP)"
[ "$DEPLOY_WEB" = true ] && log "    - Web Service (ClusterIP)"
[ "$DEPLOY_WORKER" = true ] && log "    - Worker Service (ClusterIP)"
log "  注意: Service使用ClusterIP类型，通过Ingress统一入口对外暴露"

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

# 创建 TLS Secret（如果部署 API 或 Web 服务）
if [ "$DEPLOY_API" = true ] || [ "$DEPLOY_WEB" = true ]; then
    log "检查 TLS Secret..."
    if ! kubectl get secret knowhere-tls -n "$NAMESPACE" &> /dev/null; then
        log "TLS Secret 不存在，开始创建..."
        
        # 获取脚本目录
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        CREATE_SECRET_SCRIPT="$SCRIPT_DIR/create-tls-secret.sh"
        
        if [ ! -f "$CREATE_SECRET_SCRIPT" ]; then
            error "证书创建脚本不存在: $CREATE_SECRET_SCRIPT"
        fi
        
        # 设置执行权限
        chmod +x "$CREATE_SECRET_SCRIPT"
        
        # 调用证书创建脚本
        if [ -n "$SSL_CERT_FILE" ] && [ -n "$SSL_KEY_FILE" ]; then
            log "使用本地证书文件创建 Secret..."
            CERT_FILE="$SSL_CERT_FILE" KEY_FILE="$SSL_KEY_FILE" \
                NAMESPACE="$NAMESPACE" \
                "$CREATE_SECRET_SCRIPT"
        else
            log "使用阿里云证书ID创建 Secret..."
            CERT_ID="$SSL_CERT_ID" \
                NAMESPACE="$NAMESPACE" \
                "$CREATE_SECRET_SCRIPT" || {
                warn "自动创建证书 Secret 失败，请手动创建："
                warn "  方式1: 使用证书文件"
                warn "    CERT_FILE=/path/to/cert.crt KEY_FILE=/path/to/cert.key $CREATE_SECRET_SCRIPT"
                warn "  方式2: 手动创建"
                warn "    kubectl create secret tls knowhere-tls --cert=/path/to/cert.crt --key=/path/to/cert.key -n $NAMESPACE"
                warn "  继续部署，但 HTTPS 可能无法正常工作"
            }
        fi
    else
        log "TLS Secret 已存在，跳过创建"
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

# 应用PodDisruptionBudget
log "创建PodDisruptionBudget..."
if [ "$DEPLOY_API" = true ]; then
    log "  部署 API PodDisruptionBudget"
    envsubst < "$SCRIPT_DIR/../kubernetes/base/pdb-api.yaml" | kubectl apply -f -
fi
if [ "$DEPLOY_WEB" = true ]; then
    log "  部署 Web PodDisruptionBudget"
    envsubst < "$SCRIPT_DIR/../kubernetes/base/pdb-web.yaml" | kubectl apply -f -
fi
if [ "$DEPLOY_WORKER" = true ]; then
    log "  部署 Worker PodDisruptionBudget"
    envsubst < "$SCRIPT_DIR/../kubernetes/base/pdb-worker.yaml" | kubectl apply -f -
fi

# 应用HPA
log "创建HorizontalPodAutoscaler..."
if [ "$DEPLOY_API" = true ]; then
    log "  部署 API HPA"
    envsubst < "$SCRIPT_DIR/../kubernetes/base/hpa-api.yaml" | kubectl apply -f -
fi
if [ "$DEPLOY_WEB" = true ]; then
    log "  部署 Web HPA"
    envsubst < "$SCRIPT_DIR/../kubernetes/base/hpa-web.yaml" | kubectl apply -f -
fi
if [ "$DEPLOY_WORKER" = true ]; then
    log "  部署 Worker HPA"
    envsubst < "$SCRIPT_DIR/../kubernetes/base/hpa-worker.yaml" | kubectl apply -f -
fi

log "部署完成！"
log ""
log "验证部署状态："
kubectl get pods -n "$NAMESPACE"
kubectl get svc -n "$NAMESPACE"
kubectl get ingress -n "$NAMESPACE"

# 验证 TLS Secret（如果部署了 API 或 Web）
if [ "$DEPLOY_API" = true ] || [ "$DEPLOY_WEB" = true ]; then
    log ""
    log "验证 HTTPS 配置："
    if kubectl get secret knowhere-tls -n "$NAMESPACE" &> /dev/null; then
        log "  ✓ TLS Secret 'knowhere-tls' 已存在"
        
        # 检查证书有效期（如果可能）
        CERT_DATA=$(kubectl get secret knowhere-tls -n "$NAMESPACE" -o jsonpath='{.data.tls\.crt}' 2>/dev/null || echo "")
        if [ -n "$CERT_DATA" ] && command -v openssl &> /dev/null; then
            CERT_INFO=$(echo "$CERT_DATA" | base64 -d 2>/dev/null | openssl x509 -noout -dates 2>/dev/null || echo "")
            if [ -n "$CERT_INFO" ]; then
                log "  证书信息："
                echo "$CERT_INFO" | sed 's/^/    /'
            fi
        fi
    else
        warn "  ⚠ TLS Secret 'knowhere-tls' 不存在，HTTPS 可能无法正常工作"
        warn "  请运行以下命令创建："
        warn "    CERT_FILE=/path/to/cert.crt KEY_FILE=/path/to/cert.key ./create-tls-secret.sh"
    fi
fi

kubectl get hpa -n "$NAMESPACE" 2>/dev/null || log "  HPA未安装或metrics-server未就绪"
kubectl get pdb -n "$NAMESPACE" 2>/dev/null || log "  PDB未安装"
log ""
log "提示：如果Secret需要更新（如MQ用户名密码、Redis密码），请使用以下命令："
log "  kubectl create secret generic knowhere-secrets \\"
log "    --from-literal=rabbitmq-username='<base64-decoded-username>' \\"
log "    --from-literal=rabbitmq-password='<base64-decoded-password>' \\"
log "    --from-literal=redis-password='KHTlQIRTLYbE^gvIoKvw&ARM' \\"
log "    ... (其他字段) \\"
log "    --namespace=$NAMESPACE \\"
log "    --dry-run=client -o yaml | kubectl apply -f -"

