# RDS Serverless PostgreSQL配置

# RDS Serverless实例（使用PostgreSQL Serverless）
resource "alicloud_db_instance" "postgres" {
  engine           = "PostgreSQL"
  engine_version   = "15.0"
  instance_type    = "pg.n2.serverless.1c"
  instance_storage = 20
  instance_name    = "${var.project_name}-${var.environment}-postgres"
  db_instance_storage_type = "cloud_essd"

  # 网络配置
  vpc_id     = alicloud_vpc.main.id
  vswitch_id = alicloud_vswitch.private[0].id
  
  # 安全组
  security_group_ids = [alicloud_security_group.rds.id]

  # 加密（暂时注释，等 KMS 授权后再启用）
  # encryption_key = alicloud_kms_key.rds.id

  # 删除保护
  deletion_protection = var.environment == "prod" ? true : false

  tags = {
    Name        = "${var.project_name}-${var.environment}-postgres"
    Environment = var.environment
    Project     = var.project_name
  }

  # 对于已导入的资源，忽略配置差异以避免更新错误
  lifecycle {
    ignore_changes = [
      instance_charge_type,
      db_instance_storage_type,
      bursting_enabled
    ]
  }
}

# KMS密钥 - 用于RDS加密
resource "alicloud_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  pending_window_in_days  = 7
  status                  = "Enabled"
  # automatic_rotation 参数在当前版本不支持，移除
  # rotation_interval   = "365d"

  tags = {
    Name        = "${var.project_name}-${var.environment}-rds-kms-key"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RDS安全组
resource "alicloud_security_group" "rds" {
  security_group_name = "${var.project_name}-${var.environment}-rds-sg"
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

# 变量定义在 variables.tf 中

# Redis Serverless配置
# 查找支持 Redis 的可用区
data "alicloud_kvstore_zones" "available" {
  engine = "Redis"
}

resource "alicloud_kvstore_instance" "redis" {
  db_instance_name     = "${var.project_name}-${var.environment}-redis-serverless"
  instance_class    = "redis.master.small.default"
  instance_type    = "Redis"
  engine_version    = "5.0"  # 本地磁盘实例支持 5.0
  payment_type      = "PostPaid"  # PostPaid 或 PrePaid
  # 使用支持 Redis 的可用区（优先使用第一个支持 Redis 的可用区）
  zone_id           = length(data.alicloud_kvstore_zones.available.zones) > 0 ? data.alicloud_kvstore_zones.available.zones[0].id : data.alicloud_zones.available.zones[0].id
  # 使用该可用区对应的 vSwitch（如果 private[0] 在该可用区则使用，否则使用 private[1]）
  vswitch_id        = (
    length(data.alicloud_kvstore_zones.available.zones) > 0 && 
    data.alicloud_kvstore_zones.available.zones[0].id == data.alicloud_zones.available.zones[0].id ? 
    alicloud_vswitch.private[0].id : 
    (length(alicloud_vswitch.private) > 1 ? alicloud_vswitch.private[1].id : alicloud_vswitch.private[0].id)
  )
  security_group_id = alicloud_security_group.redis.id

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-serverless"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Redis安全组
resource "alicloud_security_group" "redis" {
  security_group_name = "${var.project_name}-${var.environment}-redis-sg"
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

