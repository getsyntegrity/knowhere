#!/bin/bash
# 从 Terraform outputs 生成环境变量配置
# 用于生成 Kubernetes Secrets 和 ConfigMap
#
# 使用方法:
#   cd deploy/aliyun/ack/terraform
#   ./scripts/generate-env-vars.sh [output-format]
#
# output-format 可选值:
#   - kubectl: 生成 kubectl 命令（默认）
#   - yaml: 生成 YAML 文件
#   - env: 生成 .env 文件格式

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# 检查输出格式
OUTPUT_FORMAT=${1:-kubectl}
if [[ ! "$OUTPUT_FORMAT" =~ ^(kubectl|yaml|env)$ ]]; then
    error "输出格式必须是: kubectl, yaml 或 env"
fi

cd "$TERRAFORM_DIR"

# 检查 Terraform 是否已初始化
if [ ! -d ".terraform" ]; then
    error "Terraform 未初始化，请先运行: terraform init -backend-config=backend-config.prod"
fi

# 检查是否有 Terraform state
if ! terraform output &>/dev/null; then
    error "无法读取 Terraform outputs，请先运行: terraform apply"
fi

log "从 Terraform outputs 读取环境变量..."

# 读取基础设施配置（非敏感）
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null || echo "")
RDS_PORT=$(terraform output -raw rds_port 2>/dev/null || echo "")
REDIS_HOST=$(terraform output -raw redis_host 2>/dev/null || echo "")
REDIS_PORT=$(terraform output -raw redis_port 2>/dev/null || echo "")
REDIS_DATABASE=$(terraform output -raw redis_database 2>/dev/null || echo "0")
RABBITMQ_USERNAME=$(terraform output -raw rabbitmq_username 2>/dev/null || echo "admin")
RABBITMQ_PORT=$(terraform output -raw rabbitmq_port 2>/dev/null || echo "5672")
RABBITMQ_VHOST=$(terraform output -raw rabbitmq_virtual_host 2>/dev/null || echo "/")
OSS_BUCKET_NAME=$(terraform output -raw oss_bucket_name 2>/dev/null || echo "")
S3_TYPE=$(terraform output -raw s3_type 2>/dev/null || echo "oss")
S3_REGION=$(terraform output -raw s3_region 2>/dev/null || echo "")
S3_USE_SSL=$(terraform output -raw s3_use_ssl 2>/dev/null || echo "true")
S3_ADDRESSING_STYLE=$(terraform output -raw s3_addressing_style 2>/dev/null || echo "auto")
OSS_ENDPOINT=$(terraform output -raw oss_endpoint 2>/dev/null || echo "")
S3_ENDPOINT_URL=$(terraform output -raw s3_endpoint_url 2>/dev/null || echo "")
S3_PRIVATE_DOMAIN=$(terraform output -raw s3_private_domain 2>/dev/null || echo "")
S3_TEMP_PATH=$(terraform output -raw s3_temp_path 2>/dev/null || echo "/tmp")

# 读取应用配置（非敏感）
APP_TITLE=$(terraform output -raw app_title 2>/dev/null || echo "")
APP_DESCRIPTION=$(terraform output -raw app_description 2>/dev/null || echo "")
APP_VERSION=$(terraform output -raw app_version 2>/dev/null || echo "")
ENVIRONMENT=$(terraform output -raw environment 2>/dev/null || echo "prod")
DEBUG=$(terraform output -raw debug 2>/dev/null || echo "false")
LOG_LEVEL=$(terraform output -raw log_level 2>/dev/null || echo "INFO")
TMP_PATH=$(terraform output -raw tmp_path 2>/dev/null || echo "/tmp/aismart_bid")
FONT_PATH=$(terraform output -raw font_path 2>/dev/null || echo "/usr/share/fonts")
CHROMEDRIVER_PATH=$(terraform output -raw chromedriver_path 2>/dev/null || echo "/usr/bin/chromedriver")
ALGORITHM=$(terraform output -raw algorithm 2>/dev/null || echo "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES=$(terraform output -raw access_token_expire_minutes 2>/dev/null || echo "10080")
SUPPORTED_EXTENSIONS=$(terraform output -raw supported_extensions 2>/dev/null || echo "")
MAX_FILE_SIZE=$(terraform output -raw max_file_size 2>/dev/null || echo "104857600")
MAX_IMAGE_SIZE=$(terraform output -raw max_image_size 2>/dev/null || echo "10485760")
MIN_CONFIDENCE_THRESHOLD=$(terraform output -raw min_confidence_threshold 2>/dev/null || echo "0.05")
HIGH_IOU_THRESHOLD=$(terraform output -raw high_iou_threshold 2>/dev/null || echo "0.9")
DEFAULT_EMBEDDING_DIM=$(terraform output -raw default_embedding_dim 2>/dev/null || echo "1024")
DEFAULT_TOP_K=$(terraform output -raw default_top_k 2>/dev/null || echo "5")
DEFAULT_BATCH_SIZE=$(terraform output -raw default_batch_size 2>/dev/null || echo "32")
DEFAULT_EPOCHS=$(terraform output -raw default_epochs 2>/dev/null || echo "3")
DEFAULT_THRESHOLD=$(terraform output -raw default_threshold 2>/dev/null || echo "0.5")
FREE_PLAN_INITIAL_CREDITS=$(terraform output -raw free_plan_initial_credits 2>/dev/null || echo "100")
USERS_DATA_PATH=$(terraform output -raw users_data_path 2>/dev/null || echo "/opt/knowhere/users")
DB_SSL_MODE=$(terraform output -raw db_ssl_mode 2>/dev/null || echo "prefer")
MESSAGE_BROKER_TYPE=$(terraform output -raw message_broker_type 2>/dev/null || echo "rabbitmq")
CELERY_RESULT_BACKEND=$(terraform output -raw celery_result_backend 2>/dev/null || echo "rpc://")
SNS_SIGNATURE_VERIFICATION=$(terraform output -raw sns_signature_verification 2>/dev/null || echo "true")
OSS_EVENT_VERIFY_SIGNATURE=$(terraform output -raw oss_event_verify_signature 2>/dev/null || echo "true")
SMTP_HOST=$(terraform output -raw smtp_host 2>/dev/null || echo "")
SMTP_PORT=$(terraform output -raw smtp_port 2>/dev/null || echo "587")
SMTP_USER=$(terraform output -raw smtp_user 2>/dev/null || echo "")
EMAILS_FROM_EMAIL=$(terraform output -raw emails_from_email 2>/dev/null || echo "")
EMAILS_FROM_NAME=$(terraform output -raw emails_from_name 2>/dev/null || echo "")
DS_URL=$(terraform output -raw ds_url 2>/dev/null || echo "")
ALI_URL=$(terraform output -raw ali_url 2>/dev/null || echo "")
ARK_URL=$(terraform output -raw ark_url 2>/dev/null || echo "")
EMBEDDING_MODEL=$(terraform output -raw embedding_model 2>/dev/null || echo "")
NORMAL_MODEL=$(terraform output -raw normal_model 2>/dev/null || echo "")
IMAGE_MODEL=$(terraform output -raw image_model 2>/dev/null || echo "")
MINERU_URL=$(terraform output -raw mineru_url 2>/dev/null || echo "")

# 读取敏感信息（需要特殊处理）
log "读取敏感信息（标记为敏感）..."

# 构建 DATABASE_URL
DB_PASSWORD=$(terraform output -raw db_password 2>/dev/null || echo "")
if [ -n "$RDS_ENDPOINT" ] && [ -n "$RDS_PORT" ] && [ -n "$DB_PASSWORD" ]; then
    DATABASE_URL="postgresql+asyncpg://postgres:${DB_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/knowhere"
else
    warn "无法构建 DATABASE_URL，请检查 RDS 配置"
    DATABASE_URL=""
fi

# 构建 CELERY_BROKER_URL
if [ -n "$RABBITMQ_USERNAME" ]; then
    RABBITMQ_PASSWORD=$(terraform output -raw rabbitmq_password 2>/dev/null || echo "")
    # 注意：RabbitMQ endpoint 需要通过控制台或 API 获取
    RABBITMQ_HOST="请通过阿里云控制台或API获取RabbitMQ端点"
    CELERY_BROKER_URL="amqp://${RABBITMQ_USERNAME}:${RABBITMQ_PASSWORD}@${RABBITMQ_HOST}:${RABBITMQ_PORT}/"
else
    CELERY_BROKER_URL=""
fi

# 根据输出格式生成配置
case "$OUTPUT_FORMAT" in
    kubectl)
        log "生成 kubectl 命令..."
        echo ""
        echo "# 创建 Kubernetes Secrets"
        echo "kubectl create secret generic knowhere-secrets \\"
        echo "  --from-literal=database-url='${DATABASE_URL}' \\"
        echo "  --from-literal=redis-host='${REDIS_HOST}' \\"
        echo "  --from-literal=redis-port='${REDIS_PORT}' \\"
        echo "  --from-literal=redis-password='$(terraform output -raw redis_password 2>/dev/null || echo "")' \\"
        echo "  --from-literal=redis-database='${REDIS_DATABASE}' \\"
        echo "  --from-literal=rabbitmq-host='${RABBITMQ_HOST}' \\"
        echo "  --from-literal=rabbitmq-username='${RABBITMQ_USERNAME}' \\"
        echo "  --from-literal=rabbitmq-password='$(terraform output -raw rabbitmq_password 2>/dev/null || echo "")' \\"
        echo "  --from-literal=rabbitmq-port='${RABBITMQ_PORT}' \\"
        echo "  --from-literal=rabbitmq-vhost='${RABBITMQ_VHOST}' \\"
        echo "  --from-literal=celery-broker-url='${CELERY_BROKER_URL}' \\"
        echo "  --from-literal=s3-access-key-id='$(terraform output -raw s3_access_key_id 2>/dev/null || echo "")' \\"
        echo "  --from-literal=s3-secret-access-key='$(terraform output -raw s3_secret_access_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=secret-key='$(terraform output -raw app_secret_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=users-verify-token-secret='$(terraform output -raw users_verify_token_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=users-reset-password-token-secret='$(terraform output -raw users_reset_password_token_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=webhook-signing-secret='$(terraform output -raw webhook_signing_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=s3-webhook-auth-token='$(terraform output -raw s3_webhook_auth_token 2>/dev/null || echo "")' \\"
        echo "  --from-literal=oss-event-callback-key='$(terraform output -raw oss_event_callback_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=stripe-secret-key='$(terraform output -raw stripe_secret_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=stripe-publishable-key='$(terraform output -raw stripe_publishable_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=stripe-webhook-secret='$(terraform output -raw stripe_webhook_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=posthog-key='$(terraform output -raw posthog_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=resend-api-key='$(terraform output -raw resend_api_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=moesif-application-id='$(terraform output -raw moesif_application_id 2>/dev/null || echo "")' \\"
        echo "  --from-literal=google-client-id='$(terraform output -raw google_client_id 2>/dev/null || echo "")' \\"
        echo "  --from-literal=google-client-secret='$(terraform output -raw google_client_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=github-client-id='$(terraform output -raw github_client_id 2>/dev/null || echo "")' \\"
        echo "  --from-literal=github-client-secret='$(terraform output -raw github_client_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=apple-client-id='$(terraform output -raw apple_client_id 2>/dev/null || echo "")' \\"
        echo "  --from-literal=apple-client-secret='$(terraform output -raw apple_client_secret 2>/dev/null || echo "")' \\"
        echo "  --from-literal=smtp-password='$(terraform output -raw smtp_password 2>/dev/null || echo "")' \\"
        echo "  --from-literal=ds-key='$(terraform output -raw ds_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=ali-api-key='$(terraform output -raw ali_api_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=ark-api-key='$(terraform output -raw ark_api_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=gpt-api-key='$(terraform output -raw gpt_api_key 2>/dev/null || echo "")' \\"
        echo "  --from-literal=mineru-api-key='$(terraform output -raw mineru_api_key 2>/dev/null || echo "")' \\"
        echo "  --namespace=knowhere \\"
        echo "  --dry-run=client -o yaml | kubectl apply -f -"
        echo ""
        echo "# 创建或更新 ConfigMap"
        echo "kubectl create configmap knowhere-config \\"
        echo "  --from-literal=ENVIRONMENT='${ENVIRONMENT}' \\"
        echo "  --from-literal=LOG_LEVEL='${LOG_LEVEL}' \\"
        echo "  --from-literal=DEBUG='${DEBUG}' \\"
        echo "  --from-literal=PYTHONUNBUFFERED='1' \\"
        echo "  --from-literal=NODE_ENV='production' \\"
        echo "  --from-literal=NEXT_TELEMETRY_DISABLED='1' \\"
        echo "  --from-literal=APP_TITLE='${APP_TITLE}' \\"
        echo "  --from-literal=APP_VERSION='${APP_VERSION}' \\"
        echo "  --from-literal=APP_DESCRIPTION='${APP_DESCRIPTION}' \\"
        echo "  --from-literal=TMP_PATH='${TMP_PATH}' \\"
        echo "  --from-literal=FONT_PATH='${FONT_PATH}' \\"
        echo "  --from-literal=CHROMEDRIVER_PATH='${CHROMEDRIVER_PATH}' \\"
        echo "  --from-literal=ALGORITHM='${ALGORITHM}' \\"
        echo "  --from-literal=ACCESS_TOKEN_EXPIRE_MINUTES='${ACCESS_TOKEN_EXPIRE_MINUTES}' \\"
        echo "  --from-literal=DB_SSL_MODE='${DB_SSL_MODE}' \\"
        echo "  --from-literal=REDIS_DATABASE='${REDIS_DATABASE}' \\"
        echo "  --from-literal=RABBITMQ_PORT='${RABBITMQ_PORT}' \\"
        echo "  --from-literal=RABBITMQ_VHOST='${RABBITMQ_VHOST}' \\"
        echo "  --from-literal=MESSAGE_BROKER_TYPE='${MESSAGE_BROKER_TYPE}' \\"
        echo "  --from-literal=CELERY_RESULT_BACKEND='${CELERY_RESULT_BACKEND}' \\"
        echo "  --from-literal=S3_TYPE='${S3_TYPE}' \\"
        echo "  --from-literal=S3_BUCKET_NAME='${OSS_BUCKET_NAME}' \\"
        echo "  --from-literal=S3_ENDPOINT_URL='${S3_ENDPOINT_URL}' \\"
        echo "  --from-literal=S3_PRIVATE_DOMAIN='${S3_PRIVATE_DOMAIN}' \\"
        echo "  --from-literal=S3_TEMP_PATH='${S3_TEMP_PATH}' \\"
        echo "  --from-literal=S3_REGION='${S3_REGION}' \\"
        echo "  --from-literal=S3_USE_SSL='${S3_USE_SSL}' \\"
        echo "  --from-literal=S3_ADDRESSING_STYLE='${S3_ADDRESSING_STYLE}' \\"
        echo "  --from-literal=OSS_ENDPOINT='${OSS_ENDPOINT}' \\"
        echo "  --from-literal=SNS_SIGNATURE_VERIFICATION='${SNS_SIGNATURE_VERIFICATION}' \\"
        echo "  --from-literal=OSS_EVENT_VERIFY_SIGNATURE='${OSS_EVENT_VERIFY_SIGNATURE}' \\"
        echo "  --from-literal=SUPPORTED_EXTENSIONS='${SUPPORTED_EXTENSIONS}' \\"
        echo "  --from-literal=MAX_FILE_SIZE='${MAX_FILE_SIZE}' \\"
        echo "  --from-literal=MAX_IMAGE_SIZE='${MAX_IMAGE_SIZE}' \\"
        echo "  --from-literal=MIN_CONFIDENCE_THRESHOLD='${MIN_CONFIDENCE_THRESHOLD}' \\"
        echo "  --from-literal=HIGH_IOU_THRESHOLD='${HIGH_IOU_THRESHOLD}' \\"
        echo "  --from-literal=DEFAULT_EMBEDDING_DIM='${DEFAULT_EMBEDDING_DIM}' \\"
        echo "  --from-literal=DEFAULT_TOP_K='${DEFAULT_TOP_K}' \\"
        echo "  --from-literal=DEFAULT_BATCH_SIZE='${DEFAULT_BATCH_SIZE}' \\"
        echo "  --from-literal=DEFAULT_EPOCHS='${DEFAULT_EPOCHS}' \\"
        echo "  --from-literal=DEFAULT_THRESHOLD='${DEFAULT_THRESHOLD}' \\"
        echo "  --from-literal=FREE_PLAN_INITIAL_CREDITS='${FREE_PLAN_INITIAL_CREDITS}' \\"
        echo "  --from-literal=USERS_DATA_PATH='${USERS_DATA_PATH}' \\"
        echo "  --from-literal=SMTP_HOST='${SMTP_HOST}' \\"
        echo "  --from-literal=SMTP_PORT='${SMTP_PORT}' \\"
        echo "  --from-literal=SMTP_USER='${SMTP_USER}' \\"
        echo "  --from-literal=EMAILS_FROM_EMAIL='${EMAILS_FROM_EMAIL}' \\"
        echo "  --from-literal=EMAILS_FROM_NAME='${EMAILS_FROM_NAME}' \\"
        echo "  --from-literal=DS_URL='${DS_URL}' \\"
        echo "  --from-literal=ALI_URL='${ALI_URL}' \\"
        echo "  --from-literal=ARK_URL='${ARK_URL}' \\"
        echo "  --from-literal=EMBEDDING_MODEL='${EMBEDDING_MODEL}' \\"
        echo "  --from-literal=NORMOL_MODEL='${NORMAL_MODEL}' \\"
        echo "  --from-literal=IMAGE_MODEL='${IMAGE_MODEL}' \\"
        echo "  --from-literal=MINERU_URL='${MINERU_URL}' \\"
        echo "  --namespace=knowhere \\"
        echo "  --dry-run=client -o yaml | kubectl apply -f -"
        ;;
    yaml)
        log "生成 YAML 文件..."
        warn "YAML 格式输出功能待实现"
        ;;
    env)
        log "生成 .env 文件格式..."
        warn ".env 格式输出功能待实现"
        ;;
esac

log "✅ 环境变量配置生成完成！"

