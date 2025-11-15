#!/bin/bash

# RabbitMQ 用户和权限配置脚本
# 使用阿里云 API 配置 RabbitMQ 用户和权限

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

# 获取 RabbitMQ 实例 ID
log "获取 RabbitMQ 实例信息..."
RABBITMQ_ID=$(terraform output -raw rabbitmq_instance_id 2>/dev/null || echo "")
if [ -z "$RABBITMQ_ID" ]; then
    error "无法获取 RabbitMQ 实例 ID，请先部署基础设施"
fi

log "RabbitMQ 实例 ID: ${RABBITMQ_ID}"
echo ""

# 从配置文件读取用户名和密码
TFVARS_FILE="terraform.tfvars.${ENVIRONMENT}"
if [ ! -f "$TFVARS_FILE" ]; then
    error "配置文件 ${TFVARS_FILE} 不存在"
fi

RABBITMQ_USERNAME=$(grep '^rabbitmq_username' "$TFVARS_FILE" | sed 's/.*= *"\(.*\)".*/\1/' || echo "admin")
RABBITMQ_PASSWORD=$(grep '^rabbitmq_password' "$TFVARS_FILE" | sed 's/.*= *"\(.*\)".*/\1/' || echo "")

if [ -z "$RABBITMQ_PASSWORD" ]; then
    error "无法从配置文件获取 RabbitMQ 密码"
fi

log "配置 RabbitMQ 用户..."
echo "  用户名: ${RABBITMQ_USERNAME}"
echo ""

# 注意：阿里云 AMQP API 可能不支持直接创建用户和权限
# 这里提供控制台操作的指导
warn "注意：阿里云 AMQP 服务可能不支持通过 CLI 直接创建用户和权限"
warn "请通过控制台手动配置："
echo ""
echo "1. 访问：https://amqp.console.aliyun.com/"
echo "2. 找到实例：${RABBITMQ_ID}"
echo "3. 进入实例详情 → 用户管理"
echo "4. 创建用户："
echo "   - 用户名: ${RABBITMQ_USERNAME}"
echo "   - 密码: ${RABBITMQ_PASSWORD}"
echo "5. 配置权限："
echo "   - 虚拟主机: /"
echo "   - Configure: .*"
echo "   - Write: .*"
echo "   - Read: .*"
echo ""

log "=========================================="
log "配置信息已准备"
log "=========================================="
echo ""
log "实例 ID: ${RABBITMQ_ID}"
log "用户名: ${RABBITMQ_USERNAME}"
log "密码: 已从配置文件读取"
echo ""
log "请按照上述步骤在控制台完成配置"
echo ""

