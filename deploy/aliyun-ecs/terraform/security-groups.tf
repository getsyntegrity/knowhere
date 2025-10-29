# 安全组配置

# 应用服务器安全组
resource "alicloud_security_group" "app_server" {
  count       = var.use_existing_security_group ? 0 : 1
  name        = "${var.project_name}-${var.environment}-app-server-sg"
  description = "安全组 - Knowhere应用服务器"
  vpc_id      = var.use_existing_vpc ? var.existing_vpc_id : alicloud_vpc.main[0].id
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-app-server-sg"
  })
}

# HTTP访问规则
resource "alicloud_security_group_rule" "http_ingress" {
  count             = var.use_existing_security_group ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "internet"
  policy            = "accept"
  port_range        = "80/80"
  priority          = 1
  security_group_id = alicloud_security_group.app_server[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "HTTP access"
}

# HTTPS访问规则
resource "alicloud_security_group_rule" "https_ingress" {
  count             = var.use_existing_security_group ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "internet"
  policy            = "accept"
  port_range        = "443/443"
  priority          = 1
  security_group_id = alicloud_security_group.app_server[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "HTTPS access"
}

# SSH访问规则
resource "alicloud_security_group_rule" "ssh_ingress" {
  count             = var.use_existing_security_group ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "internet"
  policy            = "accept"
  port_range        = "22/22"
  priority          = 1
  security_group_id = alicloud_security_group.app_server[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "SSH access"
}

# Backend API访问规则
resource "alicloud_security_group_rule" "api_ingress" {
  count             = var.use_existing_security_group ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "5005/5005"
  priority          = 1
  security_group_id = alicloud_security_group.app_server[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "Backend API access"
}

# Web Frontend访问规则
resource "alicloud_security_group_rule" "web_ingress" {
  count             = var.use_existing_security_group ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "3000/3000"
  priority          = 1
  security_group_id = alicloud_security_group.app_server[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "Web Frontend access"
}

# 所有出站流量规则
resource "alicloud_security_group_rule" "all_egress" {
  count             = var.use_existing_security_group ? 0 : 1
  type              = "egress"
  ip_protocol       = "all"
  nic_type          = "internet"
  policy            = "accept"
  port_range        = "-1/-1"
  priority          = 1
  security_group_id = alicloud_security_group.app_server[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "All outbound traffic"
}

# 数据库安全组（如果创建新RDS）
resource "alicloud_security_group" "database" {
  count       = var.use_existing_rds ? 0 : 1
  name        = "${var.project_name}-${var.environment}-database-sg"
  description = "Security group for database"
  vpc_id      = var.use_existing_vpc ? var.existing_vpc_id : alicloud_vpc.main[0].id
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-database-sg"
  })
}

# PostgreSQL访问规则
resource "alicloud_security_group_rule" "postgres_ingress" {
  count             = var.use_existing_rds ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "5432/5432"
  priority          = 1
  security_group_id = alicloud_security_group.database[0].id
  source_security_group_id = var.use_existing_security_group ? var.existing_security_group_id : alicloud_security_group.app_server[0].id
  description       = "PostgreSQL access"
}

# 数据库出站规则
resource "alicloud_security_group_rule" "database_egress" {
  count             = var.use_existing_rds ? 0 : 1
  type              = "egress"
  ip_protocol       = "all"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "-1/-1"
  priority          = 1
  security_group_id = alicloud_security_group.database[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "All outbound traffic"
}

# Redis安全组（如果创建新Redis）
resource "alicloud_security_group" "redis" {
  count       = var.use_existing_redis ? 0 : 1
  name        = "${var.project_name}-${var.environment}-redis-sg"
  description = "Security group for Redis"
  vpc_id      = var.use_existing_vpc ? var.existing_vpc_id : alicloud_vpc.main[0].id
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-redis-sg"
  })
}

# Redis访问规则
resource "alicloud_security_group_rule" "redis_ingress" {
  count             = var.use_existing_redis ? 0 : 1
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "6379/6379"
  priority          = 1
  security_group_id = alicloud_security_group.redis[0].id
  source_security_group_id = var.use_existing_security_group ? var.existing_security_group_id : alicloud_security_group.app_server[0].id
  description       = "Redis access"
}

# Redis出站规则
resource "alicloud_security_group_rule" "redis_egress" {
  count             = var.use_existing_redis ? 0 : 1
  type              = "egress"
  ip_protocol       = "all"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "-1/-1"
  priority          = 1
  security_group_id = alicloud_security_group.redis[0].id
  cidr_ip           = "0.0.0.0/0"
  description       = "All outbound traffic"
}

# 本地值：统一的安全组引用
locals {
  app_security_group_id = var.use_existing_security_group ? var.existing_security_group_id : alicloud_security_group.app_server[0].id
  database_security_group_id = var.use_existing_rds ? "" : alicloud_security_group.database[0].id
  redis_security_group_id = var.use_existing_redis ? "" : alicloud_security_group.redis[0].id
}

