#!/bin/bash

# AWS Secrets Manager 密钥设置脚本

set -e

# 配置变量
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
PROJECT_NAME=${PROJECT_NAME:-knowhere}

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
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
    
    log "环境检查通过"
}

# 生成随机密钥
generate_secret() {
    openssl rand -base64 32
}

# 创建或更新密钥
create_or_update_secret() {
    local secret_name=$1
    local secret_value=$2
    local description=$3
    
    if aws secretsmanager describe-secret --secret-id "$secret_name" --region $AWS_REGION &> /dev/null; then
        log "更新密钥: $secret_name"
        aws secretsmanager update-secret \
            --secret-id "$secret_name" \
            --secret-string "$secret_value" \
            --description "$description" \
            --region $AWS_REGION
    else
        log "创建密钥: $secret_name"
        aws secretsmanager create-secret \
            --name "$secret_name" \
            --secret-string "$secret_value" \
            --description "$description" \
            --region $AWS_REGION
    fi
}

# 获取Terraform输出
get_terraform_outputs() {
    log "获取Terraform输出..."
    cd deploy/aws/terraform
    
    RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
    REDIS_ENDPOINT=$(terraform output -raw redis_endpoint)
    S3_BUCKET_NAME=$(terraform output -raw s3_bucket_name)
    DOMAIN_NAME=$(terraform output -raw domain_name)
    
    cd - > /dev/null
    
    log "RDS端点: $RDS_ENDPOINT"
    log "Redis端点: $REDIS_ENDPOINT"
    log "S3存储桶: $S3_BUCKET_NAME"
    log "域名: $DOMAIN_NAME"
}

# 设置所有密钥
setup_secrets() {
    log "开始设置AWS Secrets Manager密钥..."
    
    # 获取Terraform输出
    get_terraform_outputs
    
    # 数据库URL
    local db_password=$(generate_secret)
    local database_url="postgresql+asyncpg://postgres:${db_password}@${RDS_ENDPOINT}:5432/knowhere"
    create_or_update_secret \
        "knowhere/database-url" \
        "$database_url" \
        "数据库连接URL"
    
    # 数据库密码
    create_or_update_secret \
        "knowhere/database-password" \
        "$db_password" \
        "数据库密码"
    
    # Redis配置
    create_or_update_secret \
        "knowhere/redis-host" \
        "$REDIS_ENDPOINT" \
        "Redis主机地址"
    
    create_or_update_secret \
        "knowhere/redis-password" \
        "default-redis-password" \
        "Redis密码（如果启用）"
    
    # RabbitMQ配置（如果使用）
    create_or_update_secret \
        "knowhere/rabbitmq-host" \
        "$REDIS_ENDPOINT" \
        "RabbitMQ主机地址"
    
    create_or_update_secret \
        "knowhere/rabbitmq-password" \
        "default-rabbitmq-password" \
        "RabbitMQ密码"
    
    # S3配置
    create_or_update_secret \
        "knowhere/s3-access-key" \
        "placeholder-access-key" \
        "S3访问密钥ID"
    
    create_or_update_secret \
        "knowhere/s3-secret-key" \
        "placeholder-secret-key" \
        "S3秘密访问密钥"
    
    # 应用密钥
    create_or_update_secret \
        "knowhere/secret-key" \
        "$(generate_secret)" \
        "应用密钥"
    
    # Stripe配置
    create_or_update_secret \
        "knowhere/stripe-secret-key" \
        "placeholder-stripe-secret-key" \
        "Stripe秘密密钥"
    
    # PostHog配置
    create_or_update_secret \
        "knowhere/posthog-key" \
        "placeholder-posthog-key" \
        "PostHog API密钥"
    
    # API URL
    create_or_update_secret \
        "knowhere/api-url" \
        "https://api.knowhereto.ai" \
        "API URL"
    
    # Stripe公开密钥
    create_or_update_secret \
        "knowhere/stripe-publishable-key" \
        "placeholder-stripe-publishable-key" \
        "Stripe公开密钥"
    
    log "所有密钥设置完成"
}

# 显示密钥信息
show_secrets_info() {
    log "密钥设置完成！"
    info "请手动更新以下密钥的值："
    info "- knowhere/s3-access-key"
    info "- knowhere/s3-secret-key"
    info "- knowhere/stripe-secret-key"
    info "- knowhere/posthog-key"
    info ""
    info "使用以下命令更新密钥："
    info "aws secretsmanager update-secret --secret-id knowhere/s3-access-key --secret-string 'YOUR_VALUE' --region $AWS_REGION"
}

# 主函数
main() {
    check_requirements
    setup_secrets
    show_secrets_info
}

# 运行主函数
main "$@"
