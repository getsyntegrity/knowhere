#!/bin/bash

# Terraform 初始化和验证脚本
# 用于初始化 Backend 并验证配置

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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
ENVIRONMENT=${1:-}
if [ -z "$ENVIRONMENT" ]; then
    error "请指定环境: dev, test, 或 prod"
fi

if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    error "环境必须是: dev, test, 或 prod"
fi

cd "$TERRAFORM_DIR"

log "=========================================="
log "Terraform 初始化和验证 - ${ENVIRONMENT} 环境"
log "=========================================="
echo ""

# 检查配置文件是否存在
if [ ! -f "terraform.tfvars.${ENVIRONMENT}" ]; then
    error "配置文件 terraform.tfvars.${ENVIRONMENT} 不存在"
fi

if [ ! -f "backend-config.${ENVIRONMENT}" ]; then
    error "Backend 配置文件 backend-config.${ENVIRONMENT} 不存在"
fi

# 验证必需字段
log "验证配置文件..."
MISSING_FIELDS=()

if grep -q 'access_key = "your-aliyun-access-key-id"' terraform.tfvars.${ENVIRONMENT} 2>/dev/null; then
    MISSING_FIELDS+=("access_key")
fi

if grep -q 'secret_key = "your-aliyun-secret-access-key"' terraform.tfvars.${ENVIRONMENT} 2>/dev/null; then
    MISSING_FIELDS+=("secret_key")
fi

if grep -q 'oss_access_key_id     = ""' terraform.tfvars.${ENVIRONMENT} 2>/dev/null; then
    MISSING_FIELDS+=("oss_access_key_id")
fi

if grep -q 'oss_secret_access_key = ""' terraform.tfvars.${ENVIRONMENT} 2>/dev/null; then
    MISSING_FIELDS+=("oss_secret_access_key")
fi

if [ ${#MISSING_FIELDS[@]} -gt 0 ]; then
    error "以下字段未填写: ${MISSING_FIELDS[*]}"
fi

log "✅ 配置文件验证通过"

# 检查 Terraform 是否已安装
if ! command -v terraform &> /dev/null; then
    error "Terraform 未安装，请先安装 Terraform"
fi

log "Terraform 版本: $(terraform version | head -1)"

# 初始化 Backend（如果需要）
log ""
log "步骤 1: 初始化 Backend（如果需要）"
log "注意：如果 Backend 尚未初始化，需要先运行 init-backend.sh"
read -p "是否已初始化 Backend？(y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    warn "请先运行: ./scripts/init-backend.sh ${ENVIRONMENT}"
    warn "然后重新运行此脚本"
    exit 1
fi

# 初始化 Terraform
log ""
log "步骤 2: 初始化 Terraform"
terraform init -backend-config=backend-config.${ENVIRONMENT}

# 验证配置
log ""
log "步骤 3: 验证 Terraform 配置"
terraform validate

# 格式化检查
log ""
log "步骤 4: 检查配置格式"
terraform fmt -check=true -diff=true || warn "配置文件格式需要调整（运行 terraform fmt 自动修复）"

# 规划部署（不实际执行）
log ""
log "步骤 5: 规划部署（预览）"
log "注意：这将显示将要创建的资源，但不会实际创建"
read -p "是否继续执行 terraform plan？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    APP_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null || echo "${ENVIRONMENT}-$(git rev-parse --short HEAD)")
    terraform plan \
        -var-file=terraform.tfvars.${ENVIRONMENT} \
        -var="app_version=${APP_VERSION}"
else
    log "跳过 terraform plan"
fi

log ""
log "=========================================="
log "✅ 初始化和验证完成！"
log "=========================================="
log ""
log "下一步操作："
echo ""
echo "1. 检查 terraform plan 输出，确认资源创建计划正确"
echo "2. 如果一切正常，运行以下命令应用配置："
echo ""
echo "   terraform apply -var-file=terraform.tfvars.${ENVIRONMENT} \\"
echo "     -var=\"app_version=\$(git describe --tags --exact-match HEAD 2>/dev/null || echo '${ENVIRONMENT}-\$(git rev-parse --short HEAD)')\""
echo ""
echo "3. 确认部署后，继续执行镜像构建和 Kubernetes 部署"
echo ""

