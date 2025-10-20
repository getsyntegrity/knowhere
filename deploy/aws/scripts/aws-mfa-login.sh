#!/bin/bash

# AWS MFA登录脚本
# 使用OTP密码获取临时凭证

set -e

# 配置变量
AWS_REGION=${AWS_REGION:-us-east-1}
MFA_DEVICE_ARN="arn:aws:iam::092601323290:mfa/Authenticator" # 请替换为你的MFA设备ARN
SESSION_DURATION=43200  # 12小时

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# 检查AWS CLI
if ! command -v aws &> /dev/null; then
    error "AWS CLI 未安装"
fi

# 获取MFA代码
echo -n "请输入6位MFA代码: "
read -r mfa_code

if [[ ! $mfa_code =~ ^[0-9]{6}$ ]]; then
    error "MFA代码必须是6位数字"
fi

log "正在获取临时凭证..."

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

log "临时凭证获取成功！"
log "有效期至: $EXPIRATION"

# 设置环境变量
export AWS_ACCESS_KEY_ID=$ACCESS_KEY
export AWS_SECRET_ACCESS_KEY=$SECRET_KEY
export AWS_SESSION_TOKEN=$SESSION_TOKEN
export AWS_DEFAULT_REGION=$AWS_REGION

# 验证凭证
log "验证凭证..."
aws sts get-caller-identity

log "MFA认证成功！现在可以运行部署脚本了"
echo ""
echo "运行以下命令开始部署："
echo "cd deploy/aws/terraform && terraform init && terraform plan && terraform apply"
echo "cd ../.. && ./deploy/aws/scripts/build-and-push.sh"
echo "cd deploy/aws && ./scripts/deploy.sh all"
