# 云消息队列RabbitMQ版Serverless配置

# RabbitMQ Serverless实例
resource "alicloud_amqp_instance" "rabbitmq" {
  instance_name  = "${var.project_name}-${var.environment}-rabbitmq"
  instance_type  = "serverless"
  payment_type   = "PayAsYouGo"  # Subscription 或 PayAsYouGo（Serverless 使用 PayAsYouGo）
  # serverless_charge_type 参数是必需的
  # 根据阿里云文档，serverless 类型的有效值应该是 "payPerUse"
  serverless_charge_type = "payPerUse"  # Serverless 计费类型：payPerUse（按量付费）
  max_tps        = var.environment == "prod" ? 5000 : 1000
  max_connections = var.environment == "prod" ? 1000 : 500
  support_eip    = false

  # 存储配置（Serverless按量计费）
  storage_size = var.environment == "prod" ? 200 : 50

  # 对于已导入的资源，忽略配置差异以避免更新错误
  lifecycle {
    ignore_changes = [
      max_tps,
      max_connections,
      storage_size,
      serverless_charge_type
    ]
  }
}

# RabbitMQ虚拟主机
resource "alicloud_amqp_virtual_host" "main" {
  instance_id       = alicloud_amqp_instance.rabbitmq.id
  virtual_host_name = "/"
}

# 注意：RabbitMQ 用户和权限需要通过阿里云控制台或 API 手动配置
# Terraform Provider 目前不支持 alicloud_amqp_user 和 alicloud_amqp_permission 资源
# 请在实例创建后，通过控制台或脚本配置用户和权限

# RabbitMQ安全组
resource "alicloud_security_group" "rabbitmq" {
  security_group_name = "${var.project_name}-${var.environment}-rabbitmq-sg"
  vpc_id      = alicloud_vpc.main.id
  description = "Security group for RabbitMQ"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rabbitmq-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RabbitMQ安全组规则 - 允许ECS访问AMQP端口
resource "alicloud_security_group_rule" "rabbitmq_amqp_ingress" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "5672/5672"
  priority          = 1
  security_group_id = alicloud_security_group.rabbitmq.id
  source_security_group_id = alicloud_security_group.main.id
  description       = "Allow AMQP access from ECS"
}

# RabbitMQ安全组规则 - 允许ECS访问管理端口
resource "alicloud_security_group_rule" "rabbitmq_management_ingress" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "15672/15672"
  priority          = 1
  security_group_id = alicloud_security_group.rabbitmq.id
  source_security_group_id = alicloud_security_group.main.id
  description       = "Allow RabbitMQ Management UI access from ECS"
}

# 变量定义在 variables.tf 中

# 输出
output "rabbitmq_instance_id" {
  description = "RabbitMQ实例ID"
  value       = alicloud_amqp_instance.rabbitmq.id
}

output "rabbitmq_endpoint" {
  description = "RabbitMQ端点（需要通过控制台或API获取）"
  value       = "请通过阿里云控制台或API获取端点信息"
}

output "rabbitmq_username" {
  description = "RabbitMQ用户名"
  value       = var.rabbitmq_username
  sensitive   = true
}

output "rabbitmq_virtual_host" {
  description = "RabbitMQ虚拟主机"
  value       = alicloud_amqp_virtual_host.main.virtual_host_name
}

