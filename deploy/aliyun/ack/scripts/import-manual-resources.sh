#!/bin/bash

# 导入手动创建的资源到 Terraform State
# 用法: ./import-manual-resources.sh <environment> [resource_type]
# 示例: ./import-manual-resources.sh dev ack
#       ./import-manual-resources.sh dev all

set -e

ENVIRONMENT="${1:-dev}"
RESOURCE_TYPE="${2:-all}"

if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
  echo "错误: 环境参数必须是 dev、test 或 prod"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

cd "$TERRAFORM_DIR"

# 加载环境变量
if [ -f "terraform.tfvars.${ENVIRONMENT}" ]; then
  echo "✅ 加载配置文件: terraform.tfvars.${ENVIRONMENT}"
else
  echo "❌ 错误: 找不到配置文件 terraform.tfvars.${ENVIRONMENT}"
  exit 1
fi

# 初始化 Terraform（如果需要）
if [ ! -d ".terraform" ]; then
  echo "📦 初始化 Terraform..."
  terraform init -backend-config="backend-config.${ENVIRONMENT}"
fi

echo ""
echo "=========================================="
echo "导入手动创建的资源 - ${ENVIRONMENT} 环境"
echo "=========================================="
echo ""

# 导入 ACK 集群
import_ack() {
  echo "📋 导入 ACK 集群和节点池"
  echo ""
  echo "请提供以下信息："
  read -p "ACK 集群 ID (例如: c1234567890abcdef): " CLUSTER_ID
  
  if [ -z "$CLUSTER_ID" ]; then
    echo "❌ 错误: 集群 ID 不能为空"
    return 1
  fi
  
  echo ""
  echo "正在导入 ACK 集群..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_cs_managed_kubernetes.main "$CLUSTER_ID" || {
    echo "❌ 导入集群失败"
    return 1
  }
  
  echo "✅ ACK 集群导入成功"
  echo ""
  
  read -p "节点池 ID (例如: np1234567890abcdef): " NODE_POOL_ID
  
  if [ -z "$NODE_POOL_ID" ]; then
    echo "⚠️  警告: 节点池 ID 为空，跳过节点池导入"
    return 0
  fi
  
  echo ""
  echo "正在导入节点池..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_cs_kubernetes_node_pool.main "${CLUSTER_ID}:${NODE_POOL_ID}" || {
    echo "❌ 导入节点池失败"
    return 1
  }
  
  echo "✅ 节点池导入成功"
}

# 导入 RDS 实例
import_rds() {
  echo "📋 导入 RDS PostgreSQL 实例"
  echo ""
  echo "请提供以下信息："
  read -p "RDS 实例 ID (例如: pgm-1234567890abcdef): " RDS_INSTANCE_ID
  
  if [ -z "$RDS_INSTANCE_ID" ]; then
    echo "❌ 错误: RDS 实例 ID 不能为空"
    return 1
  fi
  
  read -p "数据库名称 (默认: knowhere): " DB_NAME
  DB_NAME="${DB_NAME:-knowhere}"
  
  read -p "数据库用户名 (默认: postgres): " DB_USER
  DB_USER="${DB_USER:-postgres}"
  
  echo ""
  echo "正在导入 RDS 实例..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_db_instance.postgres "$RDS_INSTANCE_ID" || {
    echo "❌ 导入 RDS 实例失败"
    return 1
  }
  
  echo "✅ RDS 实例导入成功"
  echo ""
  
  echo "正在导入数据库..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_db_database.main "${RDS_INSTANCE_ID}/${DB_NAME}" || {
    echo "⚠️  警告: 导入数据库失败，可能需要手动导入"
  }
  
  echo "正在导入数据库用户..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_rds_account.postgres "${RDS_INSTANCE_ID}/${DB_USER}" || {
    echo "⚠️  警告: 导入数据库用户失败，可能需要手动导入"
  }
  
  echo "正在导入备份策略..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_db_backup_policy.postgres_backup "$RDS_INSTANCE_ID" || {
    echo "⚠️  警告: 导入备份策略失败，可能需要手动导入"
  }
  
  echo "✅ RDS 相关资源导入完成"
}

# 导入 RabbitMQ 实例
import_rabbitmq() {
  echo "📋 导入 RabbitMQ Serverless 实例"
  echo ""
  echo "请提供以下信息："
  read -p "RabbitMQ 实例 ID (例如: amqp-cn-xxxxx): " RABBITMQ_INSTANCE_ID
  
  if [ -z "$RABBITMQ_INSTANCE_ID" ]; then
    echo "❌ 错误: RabbitMQ 实例 ID 不能为空"
    return 1
  fi
  
  read -p "虚拟主机名称 (默认: /): " VHOST_NAME
  VHOST_NAME="${VHOST_NAME:-/}"
  
  echo ""
  echo "正在导入 RabbitMQ 实例..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_amqp_instance.rabbitmq "$RABBITMQ_INSTANCE_ID" || {
    echo "❌ 导入 RabbitMQ 实例失败"
    return 1
  }
  
  echo "✅ RabbitMQ 实例导入成功"
  echo ""
  
  echo "正在导入虚拟主机..."
  terraform import -var-file="terraform.tfvars.${ENVIRONMENT}" \
    alicloud_amqp_virtual_host.main "${RABBITMQ_INSTANCE_ID}/${VHOST_NAME}" || {
    echo "⚠️  警告: 导入虚拟主机失败，可能需要手动导入"
  }
  
  echo "✅ RabbitMQ 相关资源导入完成"
}

# 显示如何获取资源ID
show_resource_ids() {
  echo "=========================================="
  echo "如何获取资源 ID"
  echo "=========================================="
  echo ""
  echo "1. ACK 集群 ID："
  echo "   - 访问: https://cs.console.aliyun.com/"
  echo "   - 进入集群详情页，URL 中的集群 ID 或集群名称下方显示"
  echo "   - 或使用 CLI: aliyun cs GET /clusters"
  echo ""
  echo "2. 节点池 ID："
  echo "   - 在集群管理页面，进入'节点池'标签"
  echo "   - 点击节点池名称，在详情页查看 ID"
  echo "   - 或使用 CLI: aliyun cs GET /clusters/{cluster_id}/nodepools"
  echo ""
  echo "3. RDS 实例 ID："
  echo "   - 访问: https://rds.console.aliyun.com/"
  echo "   - 在实例列表中查看实例 ID（格式: pgm-xxxxx）"
  echo "   - 或使用 CLI: aliyun rds DescribeDBInstances"
  echo ""
  echo "4. RabbitMQ 实例 ID："
  echo "   - 访问: https://amqp.console.aliyun.com/"
  echo "   - 在实例列表中查看实例 ID（格式: amqp-cn-xxxxx）"
  echo "   - 或使用 CLI: aliyun amqp ListInstances"
  echo ""
}

# 主逻辑
case "$RESOURCE_TYPE" in
  ack)
    import_ack
    ;;
  rds)
    import_rds
    ;;
  rabbitmq)
    import_rabbitmq
    ;;
  all)
    show_resource_ids
    echo ""
    read -p "按 Enter 继续导入，或 Ctrl+C 退出查看资源 ID..."
    echo ""
    import_ack
    echo ""
    read -p "按 Enter 继续导入 RDS，或 Ctrl+C 跳过..."
    echo ""
    import_rds
    echo ""
    read -p "按 Enter 继续导入 RabbitMQ，或 Ctrl+C 跳过..."
    echo ""
    import_rabbitmq
    ;;
  help|--help|-h)
    echo "用法: $0 <environment> [resource_type]"
    echo ""
    echo "参数:"
    echo "  environment   环境名称 (dev|test|prod)"
    echo "  resource_type 资源类型 (ack|rds|rabbitmq|all)"
    echo ""
    echo "示例:"
    echo "  $0 dev ack          # 导入 ACK 集群"
    echo "  $0 dev rds           # 导入 RDS 实例"
    echo "  $0 dev rabbitmq      # 导入 RabbitMQ 实例"
    echo "  $0 dev all           # 导入所有资源"
    exit 0
    ;;
  *)
    echo "❌ 错误: 未知的资源类型: $RESOURCE_TYPE"
    echo "支持的类型: ack, rds, rabbitmq, all"
    echo ""
    echo "使用 '$0 help' 查看帮助信息"
    exit 1
    ;;
esac

echo ""
echo "=========================================="
echo "✅ 导入完成"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 运行 'terraform plan' 验证配置"
echo "2. 如有差异，调整 Terraform 配置"
echo "3. 运行 'terraform apply' 同步配置"
echo ""

