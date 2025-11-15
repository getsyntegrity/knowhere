#!/bin/bash

# DNS 记录配置脚本
# 使用阿里云 CLI 自动配置 DNS 记录

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

# 检查阿里云 CLI
if ! command -v aliyun &> /dev/null; then
    error "阿里云 CLI 未安装，请先安装: https://help.aliyun.com/document_detail/121258.html"
fi

cd "$TERRAFORM_DIR"

# 获取 SLB IP
log "获取 SLB IP 地址..."
SLB_ADDRESS=$(terraform output -raw slb_address 2>/dev/null || echo "")
if [ -z "$SLB_ADDRESS" ]; then
    error "无法获取 SLB IP 地址，请先部署基础设施"
fi

log "SLB IP: ${SLB_ADDRESS}"
echo ""

# 域名配置
DOMAIN_NAME="knowhereto.com"

case "$ENVIRONMENT" in
    dev)
        API_RR="apidev"
        WEB_RR="dev"
        ;;
    test)
        API_RR="apitest"
        WEB_RR="test"
        ;;
    prod)
        API_RR="api"
        WEB_RR="@"
        ;;
esac

log "配置 DNS 记录..."
echo ""

# 配置 API DNS 记录
log "配置 API DNS 记录: ${API_RR}.${DOMAIN_NAME}"
aliyun alidns AddDomainRecord \
  --DomainName "${DOMAIN_NAME}" \
  --RR "${API_RR}" \
  --Type A \
  --Value "${SLB_ADDRESS}" \
  --TTL 600

log "✅ API DNS 记录配置成功"
echo ""

# 配置 Web DNS 记录
log "配置 Web DNS 记录: ${WEB_RR}.${DOMAIN_NAME}"
aliyun alidns AddDomainRecord \
  --DomainName "${DOMAIN_NAME}" \
  --RR "${WEB_RR}" \
  --Type A \
  --Value "${SLB_ADDRESS}" \
  --TTL 600

log "✅ Web DNS 记录配置成功"
echo ""

log "=========================================="
log "DNS 配置完成！"
log "=========================================="
echo ""
log "已配置的 DNS 记录："
echo "  - ${API_RR}.${DOMAIN_NAME} → ${SLB_ADDRESS}"
echo "  - ${WEB_RR}.${DOMAIN_NAME} → ${SLB_ADDRESS}"
echo ""
warn "注意：DNS 解析可能需要几分钟时间生效"
echo ""
log "验证 DNS 配置："
echo "  dig ${API_RR}.${DOMAIN_NAME}"
echo "  dig ${WEB_RR}.${DOMAIN_NAME}"
echo ""

