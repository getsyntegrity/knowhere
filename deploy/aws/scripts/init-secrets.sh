#!/bin/bash

# Secrets Manager 初始化验证脚本
# 用于检查所有必需的secrets是否存在，并验证IAM权限

set -e

# 配置变量
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME=${PROJECT_NAME:-knowhere}
ENVIRONMENT=${ENVIRONMENT:-dev}

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

# 检查必要的环境变量和工具
check_requirements() {
    log "检查环境变量和工具..."
    
    if ! command -v aws &> /dev/null; then
        error "AWS CLI 未安装，请先安装AWS CLI"
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS凭证未配置，请先运行 'aws configure'"
    fi
    
    log "环境检查通过"
}

# 检查secret是否存在
check_secret_exists() {
    local secret_name=$1
    if aws secretsmanager describe-secret --secret-id "$secret_name" --region "$AWS_REGION" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 检查secret是否有值
check_secret_has_value() {
    local secret_name=$1
    local secret_value=$(aws secretsmanager get-secret-value --secret-id "$secret_name" --region "$AWS_REGION" --query SecretString --output text 2>/dev/null || echo "")
    if [ -z "$secret_value" ] || [ "$secret_value" == "" ]; then
        return 1
    else
        return 0
    fi
}

# 验证所有必需的secrets
verify_secrets() {
    log "验证所有必需的secrets..."
    
    local missing_secrets=()
    local empty_secrets=()
    local all_secrets=(
        "knowhere/${ENVIRONMENT}/database-url"
        "knowhere/${ENVIRONMENT}/redis-host"
        "knowhere/${ENVIRONMENT}/redis-port"
        "knowhere/${ENVIRONMENT}/redis-password"
        "knowhere/${ENVIRONMENT}/rabbitmq-host"
        "knowhere/${ENVIRONMENT}/rabbitmq-username"
        "knowhere/${ENVIRONMENT}/rabbitmq-password"
        "knowhere/${ENVIRONMENT}/s3-access-key"
        "knowhere/${ENVIRONMENT}/s3-secret-key"
        "knowhere/${ENVIRONMENT}/secret-key"
        "knowhere/${ENVIRONMENT}/stripe-secret-key"
        "knowhere/${ENVIRONMENT}/stripe-publishable-key"
        "knowhere/${ENVIRONMENT}/posthog-key"
    )
    
    for secret_name in "${all_secrets[@]}"; do
        if ! check_secret_exists "$secret_name"; then
            missing_secrets+=("$secret_name")
        elif ! check_secret_has_value "$secret_name"; then
            empty_secrets+=("$secret_name")
        else
            log "✓ $secret_name 存在且有值"
        fi
    done
    
    if [ ${#missing_secrets[@]} -gt 0 ]; then
        warn "以下secrets不存在："
        for secret in "${missing_secrets[@]}"; do
            warn "  - $secret"
        done
        info ""
        info "请运行 'terraform apply' 创建这些secrets，或使用以下命令手动创建："
        info "aws secretsmanager create-secret --name \"<secret-name>\" --secret-string \"<value>\" --region $AWS_REGION"
        return 1
    fi
    
    if [ ${#empty_secrets[@]} -gt 0 ]; then
        warn "以下secrets存在但值为空："
        for secret in "${empty_secrets[@]}"; do
            warn "  - $secret"
        done
        info ""
        info "请使用以下命令更新这些secrets的值："
        info "aws secretsmanager update-secret --secret-id \"<secret-name>\" --secret-string \"<value>\" --region $AWS_REGION"
        return 1
    fi
    
    log "所有secrets验证通过！"
    return 0
}

# 验证IAM权限
verify_iam_permissions() {
    log "验证IAM权限..."
    
    local role_name="${PROJECT_NAME}-${ENVIRONMENT}-ecs-task-execution-role"
    
    # 检查角色是否存在
    if ! aws iam get-role --role-name "$role_name" &> /dev/null; then
        warn "IAM角色 '$role_name' 不存在，请先运行 'terraform apply'"
        return 1
    fi
    
    # 检查角色是否有Secrets Manager权限
    local policies=$(aws iam list-attached-role-policies --role-name "$role_name" --query 'AttachedPolicies[*].PolicyArn' --output text)
    local inline_policies=$(aws iam list-role-policies --role-name "$role_name" --query 'PolicyNames' --output text)
    
    if echo "$policies" | grep -q "AmazonECSTaskExecutionRolePolicy" || echo "$inline_policies" | grep -q ".*secrets.*manager.*access"; then
        log "✓ IAM角色 '$role_name' 有Secrets Manager访问权限"
        return 0
    else
        warn "IAM角色 '$role_name' 可能没有Secrets Manager访问权限"
        info "请确保运行了 'terraform apply' 以应用IAM权限策略"
        return 1
    fi
}

# 显示secrets信息
show_secrets_info() {
    log "显示secrets信息..."
    
    info "所有secrets的ARN："
    aws secretsmanager list-secrets \
        --region "$AWS_REGION" \
        --filters Key=name,Values="knowhere/${ENVIRONMENT}/" \
        --query 'SecretList[*].[Name,ARN]' \
        --output table || warn "无法列出secrets"
}

# 主函数
main() {
    log "开始Secrets Manager初始化验证..."
    log "环境: $ENVIRONMENT"
    log "区域: $AWS_REGION"
    log "项目: $PROJECT_NAME"
    echo ""
    
    check_requirements
    echo ""
    
    local secrets_ok=true
    local iam_ok=true
    
    if ! verify_secrets; then
        secrets_ok=false
    fi
    echo ""
    
    if ! verify_iam_permissions; then
        iam_ok=false
    fi
    echo ""
    
    if [ "$secrets_ok" = true ] && [ "$iam_ok" = true ]; then
        log "✓ 所有验证通过！可以安全部署ECS服务。"
        show_secrets_info
        return 0
    else
        error "验证失败，请修复上述问题后重试"
    fi
}

# 运行主函数
main "$@"

