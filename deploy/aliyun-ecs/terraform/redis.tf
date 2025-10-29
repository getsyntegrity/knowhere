# Redis配置

# ApsaraDB Redis实例（如果不使用现有Redis）
resource "alicloud_kvstore_instance" "main" {
  count = var.use_existing_redis ? 0 : 1

  instance_name  = "${var.project_name}-${var.environment}-redis"
  instance_class = "redis.master.small.default" # 1核1G
  instance_type  = "Redis"
  engine_version = "7.0"
  
  # 网络配置
  vpc_id     = var.use_existing_vpc ? var.existing_vpc_id : alicloud_vpc.main[0].id
  vswitch_id = var.use_existing_vpc ? data.alicloud_vswitches.existing[0].vswitches[0].id : alicloud_vswitch.private[0].id
  
  # 安全配置
  security_ips = [var.use_existing_vpc ? "0.0.0.0/0" : alicloud_vswitch.private[0].cidr_block]
  
  # 端口配置
  port = 6379
  
  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-redis"
  })
}

