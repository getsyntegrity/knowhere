# 公共配置 - 所有环境共享的配置
# 这些配置在所有环境中相同，不需要在每个tfvars文件中重复

# 公共配置变量（可在common.tfvars中设置，但通常使用默认值）
locals {
  # 项目公共配置
  project_name = var.project_name
  
  # RabbitMQ公共配置
  rabbitmq_username = var.rabbitmq_username
  
  # 资源命名前缀
  name_prefix = "${var.project_name}-${var.environment}"
  
  # 标签配置
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

