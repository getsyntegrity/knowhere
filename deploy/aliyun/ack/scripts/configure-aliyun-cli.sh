#!/bin/bash

# 配置阿里云 CLI 的脚本
# 从 terraform.tfvars.{environment} 读取凭证并配置

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

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

# 检查环境参数
ENVIRONMENT=${1:-dev}
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    error "环境必须是: dev, test, 或 prod"
fi

cd "$TERRAFORM_DIR"

# 检查配置文件
TFVARS_FILE="terraform.tfvars.${ENVIRONMENT}"
if [ ! -f "$TFVARS_FILE" ]; then
    error "配置文件 ${TFVARS_FILE} 不存在"
fi

log "从 ${TFVARS_FILE} 读取凭证..."

# 读取凭证
ACCESS_KEY=$(grep '^access_key' "$TFVARS_FILE" | sed 's/.*= *"\(.*\)".*/\1/' || echo "")
SECRET_KEY=$(grep '^secret_key' "$TFVARS_FILE" | sed 's/.*= *"\(.*\)".*/\1/' || echo "")
REGION=$(grep '^region' "$TFVARS_FILE" | sed 's/.*= *"\(.*\)".*/\1/' | sed 's/.*#.*//' | xargs || echo "cn-guangzhou")

if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    error "无法从配置文件读取 access_key 或 secret_key"
fi

log "配置阿里云 CLI..."
echo ""

# 配置阿里云 CLI
aliyun configure set \
  --profile default \
  --mode AK \
  --region "${REGION}" \
  --access-key-id "${ACCESS_KEY}" \
  --access-key-secret "${SECRET_KEY}"

log "✅ 配置完成！"
echo ""

# 验证配置
log "验证配置..."
aliyun configure get

echo ""
log "测试连接..."
if aliyun ecs DescribeRegions > /dev/null 2>&1; then
    log "✅ 连接成功！"
    echo ""
    log "可以使用的命令示例："
    echo "  aliyun alidns DescribeDomains"
    echo "  aliyun slb DescribeLoadBalancers --RegionId ${REGION}"
    echo "  aliyun ossutil ls"
else
    warn "连接测试失败，请检查凭证是否正确"
fi

echo ""
log "=========================================="
log "配置完成"
log "=========================================="

