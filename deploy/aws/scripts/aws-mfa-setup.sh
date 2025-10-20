#!/bin/bash

# AWS MFA配置脚本
# 用于Root账户的MFA认证

set -e

# 配置变量
AWS_REGION=${AWS_REGION:-us-east-1}
MFA_DEVICE_ARN="arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):mfa/root-account-mfa-device"
SESSION_DURATION=43200  # 12小时

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

# 检查AWS CLI是否安装
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        error "AWS CLI 未安装，请先安装: brew install awscli"
    fi
    log "AWS CLI 检查通过"
}

# 获取MFA令牌
get_mfa_token() {
    echo -n "请输入6位MFA代码: "
    read -r mfa_code
    
    if [[ ! $mfa_code =~ ^[0-9]{6}$ ]]; then
        error "MFA代码必须是6位数字"
    fi
    
    echo $mfa_code
}

# 获取临时凭证
get_temp_credentials() {
    log "获取临时凭证..."
    
    mfa_code=$(get_mfa_token)
    
    # 获取临时凭证
    temp_creds=$(aws sts get-session-token \
        --serial-number "$MFA_DEVICE_ARN" \
        --token-code "$mfa_code" \
        --duration-seconds $SESSION_DURATION \
        --output json)
    
    if [ $? -ne 0 ]; then
        error "获取临时凭证失败，请检查MFA代码"
    fi
    
    # 解析凭证
    ACCESS_KEY=$(echo $temp_creds | jq -r '.Credentials.AccessKeyId')
    SECRET_KEY=$(echo $temp_creds | jq -r '.Credentials.SecretAccessKey')
    SESSION_TOKEN=$(echo $temp_creds | jq -r '.Credentials.SessionToken')
    EXPIRATION=$(echo $temp_creds | jq -r '.Credentials.Expiration')
    
    log "临时凭证获取成功，有效期至: $EXPIRATION"
}

# 配置AWS凭证
configure_aws_credentials() {
    log "配置AWS凭证..."
    
    # 创建AWS凭证文件
    mkdir -p ~/.aws
    
    cat > ~/.aws/credentials << EOF
[default]
aws_access_key_id = $ACCESS_KEY
aws_secret_access_key = $SECRET_KEY
aws_session_token = $SESSION_TOKEN
region = $AWS_REGION
EOF
    
    cat > ~/.aws/config << EOF
[default]
region = $AWS_REGION
output = json
EOF
    
    log "AWS凭证配置完成"
}

# 验证凭证
verify_credentials() {
    log "验证凭证..."
    
    # 测试凭证是否有效
    aws sts get-caller-identity > /dev/null
    
    if [ $? -eq 0 ]; then
        log "凭证验证成功"
        info "当前身份信息:"
        aws sts get-caller-identity
    else
        error "凭证验证失败"
    fi
}

# 设置环境变量
set_env_variables() {
    log "设置环境变量..."
    
    export AWS_ACCESS_KEY_ID=$ACCESS_KEY
    export AWS_SECRET_ACCESS_KEY=$SECRET_KEY
    export AWS_SESSION_TOKEN=$SESSION_TOKEN
    export AWS_DEFAULT_REGION=$AWS_REGION
    
    # 添加到当前shell环境
    echo "export AWS_ACCESS_KEY_ID=$ACCESS_KEY" >> ~/.bashrc
    echo "export AWS_SECRET_ACCESS_KEY=$SECRET_KEY" >> ~/.bashrc
    echo "export AWS_SESSION_TOKEN=$SESSION_TOKEN" >> ~/.bashrc
    echo "export AWS_DEFAULT_REGION=$AWS_REGION" >> ~/.bashrc
    
    log "环境变量设置完成"
}

# 显示使用说明
show_usage() {
    info "MFA配置完成！"
    echo ""
    echo "使用方法："
    echo "1. 运行此脚本获取临时凭证: ./aws-mfa-setup.sh"
    echo "2. 凭证有效期为12小时"
    echo "3. 过期后需要重新运行此脚本"
    echo ""
    echo "现在可以运行部署脚本："
    echo "./deploy/aws/scripts/build-and-push.sh"
    echo "./deploy/aws/scripts/deploy.sh all"
}

# 主函数
main() {
    log "开始AWS MFA配置..."
    
    check_aws_cli
    get_temp_credentials
    configure_aws_credentials
    verify_credentials
    set_env_variables
    show_usage
}

# 运行主函数
main "$@"
