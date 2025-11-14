# 云消息队列RabbitMQ版Serverless配置

# RabbitMQ Serverless实例
resource "alicloud_amqp_instance" "rabbitmq" {
  instance_name  = "${var.project_name}-${var.environment}-rabbitmq"
  instance_type  = "serverless"
  payment_type   = "PostPaid"
  max_tps        = var.environment == "prod" ? 5000 : 1000
  max_connections = var.environment == "prod" ? 1000 : 500
  support_eip    = false

  # 网络配置
  vpc_id     = alicloud_vpc.main.id
  vswitch_id = alicloud_vswitch.private[0].id

  # 存储配置（Serverless按量计费）
  storage_size = var.environment == "prod" ? 200 : 50

  tags = {
    Name        = "${var.project_name}-${var.environment}-rabbitmq"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RabbitMQ虚拟主机
resource "alicloud_amqp_virtual_host" "main" {
  instance_id       = alicloud_amqp_instance.rabbitmq.id
  virtual_host_name = "/"
}

# RabbitMQ用户
resource "alicloud_amqp_user" "main" {
  instance_id  = alicloud_amqp_instance.rabbitmq.id
  password     = var.rabbitmq_password
  user_name    = var.rabbitmq_username
  description  = "RabbitMQ user for ${var.project_name}"
}

# RabbitMQ用户权限
resource "alicloud_amqp_permission" "main" {
  instance_id     = alicloud_amqp_instance.rabbitmq.id
  user_name       = alicloud_amqp_user.main.user_name
  virtual_host    = alicloud_amqp_virtual_host.main.virtual_host_name
  configure       = ".*"
  read            = ".*"
  write           = ".*"
}

# RabbitMQ安全组
resource "alicloud_security_group" "rabbitmq" {
  name        = "${var.project_name}-${var.environment}-rabbitmq-sg"
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

# 变量
variable "rabbitmq_username" {
  description = "RabbitMQ用户名"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "rabbitmq_password" {
  description = "RabbitMQ密码"
  type        = string
  sensitive   = true
}

variable "app_version" {
  description = "应用版本号（从Git Tag或commit hash获取）"
  type        = string
  default     = "dev"
}

# 输出
output "rabbitmq_endpoint" {
  description = "RabbitMQ端点"
  value       = alicloud_amqp_instance.rabbitmq.endpoint
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

