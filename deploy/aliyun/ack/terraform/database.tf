# RDS Serverless PostgreSQL配置

# RDS Serverless实例（使用PostgreSQL Serverless）
resource "alicloud_db_instance" "postgres" {
  engine           = "PostgreSQL"
  engine_version   = "15.0"
  instance_type    = "pg.n2.serverless.1c"
  instance_storage = 20
  instance_name    = "${var.project_name}-${var.environment}-postgres"

  # Serverless配置
  db_instance_class = "pg.n2.serverless.1c"
  
  # 网络配置
  vpc_id     = alicloud_vpc.main.id
  vswitch_id = alicloud_vswitch.private[0].id
  
  # 安全组
  security_group_ids = [alicloud_security_group.rds.id]

  # 数据库配置
  db_name  = "knowhere"
  db_user  = "postgres"
  db_pass  = var.db_password

  # 备份配置
  backup_time      = "03:00Z-04:00Z"
  backup_period    = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  retention_period = 30

  # 加密
  encryption_key = alicloud_kms_key.rds.id

  # 删除保护
  deletion_protection = var.environment == "prod" ? true : false

  tags = {
    Name        = "${var.project_name}-${var.environment}-postgres"
    Environment = var.environment
    Project     = var.project_name
  }
}

# KMS密钥 - 用于RDS加密
resource "alicloud_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  pending_window_in_days  = 7
  status                  = "Enabled"
  automatic_rotation      = "Enabled"
  rotation_interval       = "365d"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rds-kms-key"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RDS安全组
resource "alicloud_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-rds-sg"
  vpc_id      = alicloud_vpc.main.id
  description = "Security group for RDS PostgreSQL"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rds-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RDS安全组规则 - 允许ECS访问
resource "alicloud_security_group_rule" "rds_ingress" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "5432/5432"
  priority          = 1
  security_group_id = alicloud_security_group.rds.id
  source_security_group_id = alicloud_security_group.main.id
  description       = "Allow PostgreSQL access from ECS"
}

# 变量
variable "db_password" {
  description = "数据库密码"
  type        = string
  sensitive   = true
}

# Redis Serverless配置
resource "alicloud_kvstore_instance" "redis" {
  instance_name     = "${var.project_name}-${var.environment}-redis-serverless"
  instance_class    = "redis.master.small.default"
  instance_type    = "Redis"
  engine_version    = "7.0"
  payment_type      = "PostPaid"
  vpc_id            = alicloud_vpc.main.id
  vswitch_id        = alicloud_vswitch.private[0].id
  security_group_id = alicloud_security_group.redis.id
  
  # Serverless配置（按量付费）
  instance_charge_type = "PostPaid"
  
  # 自动备份
  backup_time      = "03:00Z-04:00Z"
  backup_period    = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  backup_retention_period = 7

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-serverless"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Redis安全组
resource "alicloud_security_group" "redis" {
  name        = "${var.project_name}-${var.environment}-redis-sg"
  vpc_id      = alicloud_vpc.main.id
  description = "Security group for Redis"

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Redis安全组规则 - 允许ECS访问
resource "alicloud_security_group_rule" "redis_ingress" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "6379/6379"
  priority          = 1
  security_group_id = alicloud_security_group.redis.id
  source_security_group_id = alicloud_security_group.main.id
  description       = "Allow Redis access from ECS"
}

# 输出
output "rds_endpoint" {
  description = "RDS Serverless端点"
  value       = alicloud_db_instance.postgres.connection_string
}

output "rds_port" {
  description = "RDS端口"
  value       = alicloud_db_instance.postgres.port
}

output "redis_endpoint" {
  description = "Redis Serverless端点"
  value       = alicloud_kvstore_instance.redis.connection_domain
}

output "redis_port" {
  description = "Redis端口"
  value       = alicloud_kvstore_instance.redis.port
}

