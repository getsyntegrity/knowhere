#!/bin/bash
# 创建 Kubernetes Secrets 脚本
# 使用方法: ./create-secrets.sh dev

set -e

ENVIRONMENT=${1:-dev}

if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    echo "错误：环境必须是 dev、test 或 prod"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

# 设置环境变量
export ALICLOUD_ACCESS_KEY=$(grep "^access_key" "$TERRAFORM_DIR/terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)
export ALICLOUD_SECRET_KEY=$(grep "^secret_key" "$TERRAFORM_DIR/terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)

# 设置 kubeconfig
export KUBECONFIG=~/.kube/config-knowhere-$ENVIRONMENT

# 检查 kubeconfig
if [ ! -f "$KUBECONFIG" ]; then
    echo "错误：kubeconfig 文件不存在: $KUBECONFIG"
    echo "请先运行: cd $TERRAFORM_DIR && terraform output -raw kubeconfig > $KUBECONFIG"
    exit 1
fi

# 获取 Terraform 输出
cd "$TERRAFORM_DIR"

RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
RDS_PORT=$(terraform output -raw rds_port)
REDIS_ENDPOINT=$(terraform output -raw redis_endpoint)
OSS_BUCKET=$(terraform output -raw oss_bucket_name)
RABBITMQ_INSTANCE_ID=$(terraform output -raw rabbitmq_instance_id)

# 从 terraform.tfvars 获取密码和密钥
DB_PASSWORD=$(grep "^db_password" "terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)
RABBITMQ_PASSWORD=$(grep "^rabbitmq_password" "terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)
OSS_ACCESS_KEY_ID=$(grep "^oss_access_key_id" "terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)
OSS_SECRET_ACCESS_KEY=$(grep "^oss_secret_access_key" "terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)
APP_SECRET_KEY=$(grep "^app_secret_key" "terraform.tfvars.$ENVIRONMENT" | cut -d'"' -f2)

# 构建数据库 URL
DATABASE_URL="postgresql+asyncpg://postgres:${DB_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/knowhere"

# RabbitMQ 连接信息
# 注意：RabbitMQ 的 endpoint 需要通过控制台或 API 获取
# 这里使用实例 ID，实际部署时需要替换为实际的 endpoint
RABBITMQ_HOST="${RABBITMQ_INSTANCE_ID}.amqp.cn-guangzhou.aliyuncs.com"
RABBITMQ_USERNAME="admin"

echo "=== 创建 Kubernetes Secrets for $ENVIRONMENT ==="
echo ""
echo "配置信息："
echo "  RDS Endpoint: $RDS_ENDPOINT"
echo "  Redis Endpoint: $REDIS_ENDPOINT"
echo "  RabbitMQ Host: $RABBITMQ_HOST"
echo "  OSS Bucket: $OSS_BUCKET"
echo ""

# 创建命名空间（如果不存在）
kubectl create namespace knowhere --dry-run=client -o yaml | kubectl apply -f -

# 创建 Secret
kubectl create secret generic knowhere-secrets \
  --from-literal=database-url="$DATABASE_URL" \
  --from-literal=redis-host="$REDIS_ENDPOINT" \
  --from-literal=redis-port="6379" \
  --from-literal=redis-password="" \
  --from-literal=rabbitmq-host="$RABBITMQ_HOST" \
  --from-literal=rabbitmq-username="$RABBITMQ_USERNAME" \
  --from-literal=rabbitmq-password="$RABBITMQ_PASSWORD" \
  --from-literal=rabbitmq-virtual-host="/" \
  --from-literal=oss-access-key-id="$OSS_ACCESS_KEY_ID" \
  --from-literal=oss-secret-access-key="$OSS_SECRET_ACCESS_KEY" \
  --from-literal=oss-bucket-name="$OSS_BUCKET" \
  --from-literal=secret-key="$APP_SECRET_KEY" \
  --namespace=knowhere \
  --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "✅ Secrets 创建成功！"
echo ""
echo "验证："
echo "  kubectl get secrets -n knowhere"
echo "  kubectl describe secret knowhere-secrets -n knowhere"

