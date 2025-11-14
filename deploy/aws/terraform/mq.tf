# Amazon MQ for RabbitMQ配置

# RabbitMQ安全组
resource "aws_security_group" "mq" {
  name_prefix = "${var.project_name}-${var.environment}-mq-"
  vpc_id      = aws_vpc.main.id
  description = "Security group for Amazon MQ RabbitMQ"

  ingress {
    from_port       = 5671
    to_port         = 5671
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
    description     = "AMQP over TLS from ECS tasks"
  }

  ingress {
    from_port       = 15671
    to_port         = 15671
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
    description     = "RabbitMQ Management UI from ECS tasks"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-mq-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Amazon MQ for RabbitMQ Broker
resource "aws_mq_broker" "rabbitmq" {
  broker_name         = "${var.project_name}-${var.environment}-rabbitmq"
  engine_type         = "RabbitMQ"
  engine_version      = "3.12.20"
  host_instance_type  = var.environment == "prod" ? "mq.m5.large" : "mq.t3.micro"
  deployment_mode     = var.environment == "prod" ? "ACTIVE_STANDBY_MULTI_AZ" : "SINGLE_INSTANCE"
  publicly_accessible = false

  # 用户配置
  user {
    username = var.mq_username
    password = var.mq_password
  }

  # 子网配置
  subnet_ids = var.environment == "prod" ? aws_subnet.private[*].id : [aws_subnet.private[0].id]

  # 安全组
  security_groups = [aws_security_group.mq.id]

  # 日志配置
  logs {
    general = true
    audit   = false
  }

  # 加密配置
  encryption_options {
    kms_key_id        = aws_kms_key.rds.arn
    use_aws_owned_key = false
  }

  # 维护窗口
  maintenance_window_start_time {
    day_of_week = "SUNDAY"
    time_of_day = "04:00"
    time_zone   = "UTC"
  }

  # 自动小版本升级
  auto_minor_version_upgrade = true

  tags = {
    Name        = "${var.project_name}-${var.environment}-rabbitmq"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 变量
variable "mq_username" {
  description = "Amazon MQ RabbitMQ用户名"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "mq_password" {
  description = "Amazon MQ RabbitMQ密码"
  type        = string
  sensitive   = true
}

# Secrets Manager - 存储RabbitMQ连接信息
resource "aws_secretsmanager_secret" "rabbitmq_host" {
  name        = "knowhere/${var.environment}/rabbitmq-host"
  description = "Amazon MQ RabbitMQ host endpoint"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rabbitmq-host-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "rabbitmq_host" {
  secret_id     = aws_secretsmanager_secret.rabbitmq_host.id
  secret_string = replace(replace(aws_mq_broker.rabbitmq.amqp_endpoints[0], "amqps://", ""), ":5671", "")  # 直接存储host字符串
}

resource "aws_secretsmanager_secret" "rabbitmq_password" {
  name        = "knowhere/${var.environment}/rabbitmq-password"
  description = "Amazon MQ RabbitMQ password"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rabbitmq-password-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "rabbitmq_password" {
  secret_id     = aws_secretsmanager_secret.rabbitmq_password.id
  secret_string = var.mq_password
}

resource "aws_secretsmanager_secret" "rabbitmq_username" {
  name        = "knowhere/${var.environment}/rabbitmq-username"
  description = "Amazon MQ RabbitMQ username"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rabbitmq-username-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "rabbitmq_username" {
  secret_id     = aws_secretsmanager_secret.rabbitmq_username.id
  secret_string = var.mq_username
}

# 输出
output "mq_broker_endpoint" {
  description = "Amazon MQ RabbitMQ AMQPS端点"
  value       = aws_mq_broker.rabbitmq.amqp_endpoints[0]
}

output "mq_broker_management_url" {
  description = "Amazon MQ RabbitMQ管理界面URL"
  value       = "https://${aws_mq_broker.rabbitmq.instances[0].ip_address}:15671"
}

output "mq_broker_username" {
  description = "Amazon MQ RabbitMQ用户名"
  value       = var.mq_username
  sensitive   = true
}

output "mq_broker_host_secret_arn" {
  description = "RabbitMQ host Secret ARN"
  value       = aws_secretsmanager_secret.rabbitmq_host.arn
}

output "mq_broker_password_secret_arn" {
  description = "RabbitMQ password Secret ARN"
  value       = aws_secretsmanager_secret.rabbitmq_password.arn
}

