#!/bin/bash

# 准备 Terraform 配置文件脚本
# 从示例文件创建实际的配置文件

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

# Terraform 仅用于 prod 环境
ENVIRONMENT="prod"

cd "$TERRAFORM_DIR"

log "准备 ${ENVIRONMENT} 环境的配置文件..."

# 创建 Backend 配置文件
if [ ! -f "backend-config.${ENVIRONMENT}" ]; then
    log "创建 backend-config.${ENVIRONMENT}..."
    cp "backend-config.${ENVIRONMENT}.example" "backend-config.${ENVIRONMENT}"
    log "✅ backend-config.${ENVIRONMENT} 已创建"
    warn "请检查并确认 backend-config.${ENVIRONMENT} 中的配置正确"
else
    warn "backend-config.${ENVIRONMENT} 已存在，跳过创建"
fi

# 创建 Terraform 变量配置文件
if [ ! -f "terraform.tfvars.${ENVIRONMENT}" ]; then
    log "创建 terraform.tfvars.${ENVIRONMENT}..."
    cp "terraform.tfvars.example" "terraform.tfvars.${ENVIRONMENT}"
    
    # 更新环境特定的配置（仅 prod）
    sed -i '' "s/environment = \"dev\"/environment = \"prod\"/" "terraform.tfvars.${ENVIRONMENT}"
    sed -i '' "s|api_webhook_endpoint = \"\"|api_webhook_endpoint = \"https://api.knowhereto.com/v1/internal/oss-events\"|" "terraform.tfvars.${ENVIRONMENT}"
    
    log "✅ terraform.tfvars.${ENVIRONMENT} 已创建"
    warn "⚠️  重要：请编辑 terraform.tfvars.${ENVIRONMENT} 并填入以下实际值："
    echo ""
    echo "  必需配置："
    echo "    - access_key: 阿里云 AccessKey ID"
    echo "    - secret_key: 阿里云 AccessKey Secret"
    echo "    - db_password: 数据库密码（强密码）"
    echo "    - rabbitmq_password: RabbitMQ 密码（强密码）"
    echo "    - oss_access_key_id: OSS 访问密钥 ID"
    echo "    - oss_secret_access_key: OSS 秘密访问密钥"
    echo "    - app_secret_key: 应用 JWT 密钥"
    echo ""
    echo "  可选配置（根据实际需求填写）："
    echo "    - stripe_secret_key: Stripe 密钥"
    echo "    - stripe_publishable_key: Stripe 发布密钥"
    echo "    - posthog_key: PostHog 密钥"
    echo "    - resend_api_key: Resend 邮件 API 密钥"
    echo "    - moesif_application_id: Moesif 应用 ID"
    echo "    - google_client_id/secret: Google OAuth 配置"
    echo "    - github_client_id/secret: GitHub OAuth 配置"
    echo "    - apple_client_id/secret: Apple OAuth 配置"
    echo "    - smtp_*: SMTP 邮件配置"
    echo "    - ds_key, ali_api_key, ark_api_key, gpt_api_key: AI 模型 API 密钥"
    echo "    - mineru_api_key: MinerU API 密钥"
    echo "    - 以及其他环境变量（参考 apps/api/env.example）"
    echo ""
else
    warn "terraform.tfvars.${ENVIRONMENT} 已存在，跳过创建"
fi

log ""
log "=========================================="
log "✅ ${ENVIRONMENT} 环境配置文件准备完成！"
log "=========================================="
log ""
log "下一步操作："
echo ""
echo "1. 编辑配置文件，填入实际值："
echo "   - backend-config.${ENVIRONMENT}"
echo "   - terraform.tfvars.${ENVIRONMENT}"
echo ""
echo "2. 初始化 Backend（如果尚未初始化）："
echo "   cd scripts"
echo "   ./init-backend.sh prod"
echo ""
echo "3. 初始化 Terraform："
echo "   terraform init -backend-config=backend-config.prod"
echo ""
echo "4. 规划部署："
echo "   terraform plan -var-file=terraform.tfvars.prod \\"
echo "     -var=\"app_version=\$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'prod-\$(git rev-parse --short HEAD)')\""
echo ""
echo "5. 应用配置："
echo "   terraform apply -var-file=terraform.tfvars.prod \\"
echo "     -var=\"app_version=\$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'prod-\$(git rev-parse --short HEAD)')\""
echo ""
echo "6. 生成 Kubernetes Secrets 和 ConfigMap："
echo "   ./scripts/generate-env-vars.sh kubectl | bash"
echo ""

