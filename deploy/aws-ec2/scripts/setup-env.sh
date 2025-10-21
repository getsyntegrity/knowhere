#!/bin/bash

# 环境变量配置脚本
# 从Terraform获取AWS资源信息并生成.env文件

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# 配置变量
APP_DIR="/opt/knowhere"
ENV_FILE="$APP_DIR/apps/api/.env"
TERRAFORM_DIR="$APP_DIR/deploy/aws-ec2/terraform"

log "开始配置环境变量..."

# 检查Terraform目录
if [ ! -d "$TERRAFORM_DIR" ]; then
    error "Terraform目录不存在: $TERRAFORM_DIR"
    exit 1
fi

cd "$TERRAFORM_DIR"

# 从Terraform获取资源信息
log "获取AWS资源信息..."

# 获取RDS信息
RDS_ENDPOINT=$(terraform output -raw database_endpoint 2>/dev/null | cut -d: -f1 || echo "")
RDS_PORT=$(terraform output -raw database_endpoint 2>/dev/null | cut -d: -f2 || echo "5432")
RDS_DB_NAME="knowhere"

# 获取Redis信息
REDIS_ENDPOINT=$(terraform output -raw redis_endpoint 2>/dev/null || echo "")
REDIS_PORT="6379"

# 获取S3信息
S3_BUCKET_NAME=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")

# 获取实例信息
INSTANCE_PUBLIC_IP=$(terraform output -raw instance_public_ip 2>/dev/null || echo "")

# 如果Terraform输出为空，尝试从AWS CLI获取
if [ -z "$RDS_ENDPOINT" ]; then
    log "从AWS CLI获取RDS信息..."
    RDS_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier database-test --query 'DBInstances[0].Endpoint.Address' --output text 2>/dev/null || echo "")
fi

if [ -z "$REDIS_ENDPOINT" ]; then
    log "从AWS CLI获取Redis信息..."
    REDIS_ENDPOINT=$(aws elasticache describe-replication-groups --replication-group-id knowhere-test-redis --query 'ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address' --output text 2>/dev/null || echo "")
fi

if [ -z "$S3_BUCKET_NAME" ]; then
    log "从AWS CLI获取S3信息..."
    S3_BUCKET_NAME="knowhere-api-dev"
fi

# 生成随机密码
SECRET_KEY=$(openssl rand -hex 32)
USERS_VERIFY_TOKEN_SECRET=$(openssl rand -hex 32)
USERS_RESET_PASSWORD_TOKEN_SECRET=$(openssl rand -hex 32)
WEBHOOK_SIGNING_SECRET=$(openssl rand -hex 32)

# 生成.env文件
log "生成.env配置文件..."

cat > "$ENV_FILE" << EOF
# Konwhere AI知识库管理系统 - 生产环境配置
# 自动生成于 $(date)

# 系统级配置（基础设施）
DATABASE_URL=postgresql+asyncpg://postgres:${RDS_PASSWORD:-postgres123}@${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DB_NAME}
REDIS_HOST=${REDIS_ENDPOINT}
REDIS_PORT=${REDIS_PORT}
REDIS_PASSWORD=${REDIS_PASSWORD:-}
REDIS_DATABASE=0

# RabbitMQ配置（使用Redis作为消息队列）
RABBITMQ_HOST=${REDIS_ENDPOINT}
RABBITMQ_PORT=${REDIS_PORT}
RABBITMQ_USER=default
RABBITMQ_PASSWORD=${REDIS_PASSWORD:-}
RABBITMQ_VHOST=/

# Celery配置
MESSAGE_BROKER_TYPE=redis
CELERY_BROKER_URL=redis://${REDIS_ENDPOINT}:${REDIS_PORT}/0
CELERY_RESULT_BACKEND=redis://${REDIS_ENDPOINT}:${REDIS_PORT}/0

# 存储配置
S3_BUCKET_NAME=${S3_BUCKET_NAME}
S3_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
S3_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
S3_ENDPOINT_URL=https://s3.${AWS_DEFAULT_REGION:-us-west-1}.amazonaws.com
S3_PRIVATE_DOMAIN=${S3_BUCKET_NAME}.s3.${AWS_DEFAULT_REGION:-us-west-1}.amazonaws.com
S3_TEMP_PATH=/tmp

# S3高级配置
S3_REGION=${AWS_DEFAULT_REGION:-us-west-1}
S3_USE_SSL=true
S3_ADDRESSING_STYLE=auto

# 应用级配置
APP_TITLE=Konwhere AI知识库管理系统
APP_VERSION=1.0.0
APP_DESCRIPTION=基于AI的知识库管理和智能问答系统
TMP_PATH=/tmp/knowhere
FONT_PATH=/usr/share/fonts
CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 安全配置
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# 开放API管理配置
USERS_VERIFY_TOKEN_SECRET=${USERS_VERIFY_TOKEN_SECRET}
USERS_RESET_PASSWORD_TOKEN_SECRET=${USERS_RESET_PASSWORD_TOKEN_SECRET}

# Stripe 支付配置（需要手动配置）
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Webhook配置
WEBHOOK_SIGNING_SECRET=${WEBHOOK_SIGNING_SECRET}

# Resend邮件配置（需要手动配置）
RESEND_API_KEY=re_xxx

# Moesif配置（需要手动配置）
MOESIF_APPLICATION_ID=your_moesif_app_id

# PostHog配置（已禁用）
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=

# 订阅配置
FREE_PLAN_INITIAL_CREDITS=100

# S3配置
S3_UPLOADS_BUCKET=${S3_BUCKET_NAME}
S3_RESULTS_BUCKET=${S3_BUCKET_NAME}

# OAuth 配置（需要手动配置）
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
APPLE_CLIENT_ID=your-apple-client-id
APPLE_CLIENT_SECRET=your-apple-client-secret

# 邮件配置（可选）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAILS_FROM_EMAIL=your-email@gmail.com
EMAILS_FROM_NAME=Knowhere AI

# AI模型配置（需要手动配置）
DS_KEY=your-deepseek-key
DS_URL=https://api.deepseek.com/v1/chat/completions
ALI_API_KEY=your-ali-key
ALI_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ARK_API_KEY=your-ark-key
ARK_URL=https://ark.cn-beijing.volces.com/api/v3/chat/completions
GPT_API_KEY=your-openai-key
EMBEDDING_MODEL=text-embedding-v1
NORMOL_MODEL=gpt-3.5-turbo
IMAGE_MODEL=gpt-4-vision-preview

# 文件处理配置
SUPPORTED_EXTENSIONS=.doc,.docx,.pdf,.txt,.xls,.xlsx,.csv,.jpg,.png
MAX_FILE_SIZE=104857600
MAX_IMAGE_SIZE=10485760

# 模型参数配置
MIN_CONFIDENCE_THRESHOLD=0.05
HIGH_IOU_THRESHOLD=0.9
DEFAULT_EMBEDDING_DIM=1024
DEFAULT_TOP_K=5
DEFAULT_BATCH_SIZE=32
DEFAULT_EPOCHS=3
DEFAULT_THRESHOLD=0.5

# 生产环境
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# MinerU 文档解析配置（需要手动配置）
MINERU_API_KEY=your-mineru-api-key
MINERU_URL=https://mineru.net

# 兼容性字段（保留现有字段，逐步迁移）
ALL_DF_COLS=content,path,type,length,keywords,summary,know_id,tokens,extra,addtime
DEFAULT_FOLDERS=Supplementary_Files,Temporary_Files,templates,images,fragments
KB_TERM=KB_DATA
KB_VEC_TERM=KB_VECS

# 默认配置文件路径
META_PATH=app/core/config/Meta_setting.csv
CONFIG_PATH=app/core/config/config.txt
EOF

# 设置文件权限
chown appuser:appuser "$ENV_FILE"
chmod 600 "$ENV_FILE"

log "环境变量配置文件已生成: $ENV_FILE"

# 显示关键配置信息
log "关键配置信息:"
echo "  - 数据库: ${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DB_NAME}"
echo "  - Redis: ${REDIS_ENDPOINT}:${REDIS_PORT}"
echo "  - S3存储桶: ${S3_BUCKET_NAME}"
echo "  - 实例公网IP: ${INSTANCE_PUBLIC_IP}"

warn "请注意：以下配置需要手动设置："
echo "  - AI模型API密钥 (DS_KEY, ALI_API_KEY, GPT_API_KEY等)"
echo "  - Stripe支付配置"
echo "  - OAuth配置"
echo "  - 邮件配置"

log "环境变量配置完成！"
