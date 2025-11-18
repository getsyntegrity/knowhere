#!/bin/bash

# 手动配置辅助脚本
# 用于获取部署后的资源信息，便于手动配置

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

info() {
    echo -e "${BLUE}[提示]${NC} $1"
}

# 检查环境参数
ENVIRONMENT=${1:-dev}
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    error "环境必须是: dev, test, 或 prod"
    exit 1
fi

cd "$TERRAFORM_DIR"

log "=========================================="
log "手动配置辅助工具 - ${ENVIRONMENT} 环境"
log "=========================================="
echo ""

# 检查 Terraform 是否已初始化
if [ ! -d ".terraform" ]; then
    warn "Terraform 尚未初始化，请先运行: terraform init -backend-config=backend-config.${ENVIRONMENT}"
    exit 1
fi

# 获取资源信息
log "获取部署后的资源信息..."
echo ""

# SLB IP 地址（用于 DNS 配置）
SLB_ADDRESS=$(terraform output -raw slb_address 2>/dev/null || echo "未部署")
if [ "$SLB_ADDRESS" != "未部署" ]; then
    info "1. DNS 配置 - SLB IP 地址："
    echo "   ${SLB_ADDRESS}"
    echo ""
    echo "   需要配置的 DNS 记录："
    case "$ENVIRONMENT" in
        dev)
            echo "   - 主机记录: apidev, 类型: A, 值: ${SLB_ADDRESS}"
            echo "   - 主机记录: dev, 类型: A, 值: ${SLB_ADDRESS}"
            ;;
        test)
            echo "   - 主机记录: apitest, 类型: A, 值: ${SLB_ADDRESS}"
            echo "   - 主机记录: test, 类型: A, 值: ${SLB_ADDRESS}"
            ;;
        prod)
            echo "   - 主机记录: api, 类型: A, 值: ${SLB_ADDRESS}"
            echo "   - 主机记录: @, 类型: A, 值: ${SLB_ADDRESS}"
            ;;
    esac
    echo ""
    echo "   配置地址：https://dns.console.aliyun.com/"
    echo ""
else
    warn "SLB 尚未部署，无法获取 IP 地址"
fi

# OSS 存储桶名称（用于事件通知配置）
OSS_BUCKET=$(terraform output -raw oss_bucket_name 2>/dev/null || echo "未部署")
if [ "$OSS_BUCKET" != "未部署" ]; then
    info "2. OSS 事件通知配置 - 存储桶名称："
    echo "   ${OSS_BUCKET}"
    echo ""
    echo "   回调 URL："
    case "$ENVIRONMENT" in
        dev)
            echo "   https://apidev.knowhereto.com/v1/internal/oss-events"
            ;;
        test)
            echo "   https://apitest.knowhereto.com/v1/internal/oss-events"
            ;;
        prod)
            echo "   https://api.knowhereto.com/v1/internal/oss-events"
            ;;
    esac
    echo ""
    echo "   配置地址：https://oss.console.aliyun.com/bucket/detail?bucket=${OSS_BUCKET}"
    echo "   路径：基础设置 → 事件通知"
    echo ""
else
    warn "OSS 存储桶尚未部署"
fi

# RabbitMQ 实例 ID（用于用户配置）
RABBITMQ_ID=$(terraform output -raw rabbitmq_instance_id 2>/dev/null || echo "未部署")
if [ "$RABBITMQ_ID" != "未部署" ]; then
    info "3. RabbitMQ 用户配置 - 实例 ID："
    echo "   ${RABBITMQ_ID}"
    echo ""
    echo "   需要配置："
    echo "   - 用户名: admin（或从 terraform.tfvars.${ENVIRONMENT} 获取）"
    echo "   - 密码: 从 terraform.tfvars.${ENVIRONMENT} 中的 rabbitmq_password 获取"
    echo "   - 权限: Configure/Write/Read 都设置为 .*"
    echo ""
    echo "   配置地址：https://amqp.console.aliyun.com/"
    echo ""
else
    warn "RabbitMQ 实例尚未部署"
fi

# SSL 证书信息
info "4. SSL 证书配置："
echo "   证书文件位置："
echo "   - deploy/aliyun/ack/certs/server.crt"
echo "   - deploy/aliyun/ack/certs/server.key"
echo ""
echo "   配置地址：https://slb.console.aliyun.com/"
echo "   路径：证书管理 → 服务器证书"
echo ""
echo "   或使用 Let's Encrypt（推荐）："
echo "   - cert-manager 会自动申请和更新证书"
echo "   - 确保 Ingress 中已配置 cert-manager.io/cluster-issuer"
echo ""

# 输出配置命令
log "=========================================="
log "快速配置命令"
log "=========================================="
echo ""

echo "# 1. 配置 DNS（使用阿里云 CLI）"
echo "aliyun dns AddDomainRecord \\"
echo "  --DomainName knowhereto.com \\"
case "$ENVIRONMENT" in
    dev)
        echo "  --RR apidev \\"
        ;;
    test)
        echo "  --RR apitest \\"
        ;;
    prod)
        echo "  --RR api \\"
        ;;
esac
echo "  --Type A \\"
echo "  --Value ${SLB_ADDRESS} \\"
echo "  --TTL 600"
echo ""

echo "# 2. 配置 OSS 事件通知（使用脚本）"
echo "export OSS_BUCKET_NAME=\"${OSS_BUCKET}\""
case "$ENVIRONMENT" in
    dev)
        echo "export API_WEBHOOK_ENDPOINT=\"https://apidev.knowhereto.com/v1/internal/oss-events\""
        ;;
    test)
        echo "export API_WEBHOOK_ENDPOINT=\"https://apitest.knowhereto.com/v1/internal/oss-events\""
        ;;
    prod)
        echo "export API_WEBHOOK_ENDPOINT=\"https://api.knowhereto.com/v1/internal/oss-events\""
        ;;
esac
echo "cd deploy/aliyun/ack/scripts"
echo "./setup-oss-events.sh"
echo ""

echo "# 3. 查看完整配置指南"
echo "cat deploy/aliyun/MANUAL_CONFIG_GUIDE.md"
echo ""

log "=========================================="
log "完成"
log "=========================================="

