# 数据库配置

# RDS PostgreSQL实例（如果不使用现有RDS）
resource "alicloud_db_instance" "main" {
  count = var.use_existing_rds ? 0 : 1

  engine           = "PostgreSQL"
  engine_version   = "15.0"
  instance_type    = "pg.n2.medium.1" # 等同于AWS的db.t3.micro
  instance_storage = 20
  instance_name    = "${var.project_name}-${var.environment}-db"
  instance_charge_type = "Postpaid"
  
  # 网络配置
  vpc_id     = var.use_existing_vpc ? var.existing_vpc_id : alicloud_vpc.main[0].id
  vswitch_id = var.use_existing_vpc ? data.alicloud_vswitches.existing[0].vswitches[0].id : alicloud_vswitch.private[0].id
  
  # 安全配置
  security_ips = [var.use_existing_vpc ? "0.0.0.0/0" : alicloud_vswitch.private[0].cidr_block]
  
  # 数据库配置
  db_name     = "knowhere"
  db_user     = "postgres"
  db_password = random_password.db_password[0].result
  
  # 备份配置
  backup_time = "03:00Z-04:00Z"
  
  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-db"
  })
}

# 数据库密码
resource "random_password" "db_password" {
  count = var.use_existing_rds ? 0 : 1

  length  = 16
  special = true
}

