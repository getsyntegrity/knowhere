# VPC和网络配置
resource "alicloud_vpc" "main" {
  vpc_name   = "${var.project_name}-${var.environment}-vpc"
  cidr_block = "10.0.0.0/16"

  tags = {
    Name        = "${var.project_name}-${var.environment}-vpc"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 交换机 - 公共子网
resource "alicloud_vswitch" "public" {
  count = 2

  vpc_id            = alicloud_vpc.main.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  zone_id           = data.alicloud_zones.available.zones[count.index].id
  vswitch_name      = "${var.project_name}-${var.environment}-public-${count.index + 1}"

  tags = {
    Name        = "${var.project_name}-${var.environment}-public-${count.index + 1}"
    Environment = var.environment
    Type        = "Public"
  }
}

# 交换机 - 私有子网
resource "alicloud_vswitch" "private" {
  count = 2

  vpc_id            = alicloud_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  zone_id           = data.alicloud_zones.available.zones[count.index].id
  vswitch_name      = "${var.project_name}-${var.environment}-private-${count.index + 1}"

  tags = {
    Name        = "${var.project_name}-${var.environment}-private-${count.index + 1}"
    Environment = var.environment
    Type        = "Private"
  }
}

# NAT网关
resource "alicloud_nat_gateway" "main" {
  count = 2

  vpc_id           = alicloud_vpc.main.id
  nat_gateway_name = "${var.project_name}-${var.environment}-nat-${count.index + 1}"
  vswitch_id       = alicloud_vswitch.public[count.index].id
  nat_type         = "Enhanced"
  payment_type     = "PayAsYouGo"

  tags = {
    Name        = "${var.project_name}-${var.environment}-nat-${count.index + 1}"
    Environment = var.environment
  }
}

# EIP for NAT Gateway
resource "alicloud_eip_address" "nat" {
  count = 2

  bandwidth            = "100"
  internet_charge_type = "PayByBandwidth"
  payment_type         = "PayAsYouGo"

  tags = {
    Name        = "${var.project_name}-${var.environment}-nat-eip-${count.index + 1}"
    Environment = var.environment
  }
}

resource "alicloud_eip_association" "nat" {
  count = 2

  allocation_id = alicloud_eip_address.nat[count.index].id
  instance_id   = alicloud_nat_gateway.main[count.index].id
}

# 路由表
resource "alicloud_route_table" "public" {
  vpc_id           = alicloud_vpc.main.id
  route_table_name = "${var.project_name}-${var.environment}-public-rt"

  tags = {
    Name        = "${var.project_name}-${var.environment}-public-rt"
    Environment = var.environment
  }
}

resource "alicloud_route_table" "private" {
  count = 2

  vpc_id           = alicloud_vpc.main.id
  route_table_name = "${var.project_name}-${var.environment}-private-rt-${count.index + 1}"

  tags = {
    Name        = "${var.project_name}-${var.environment}-private-rt-${count.index + 1}"
    Environment = var.environment
  }
}

# 路由表关联
resource "alicloud_route_table_attachment" "public" {
  count = 2

  vswitch_id     = alicloud_vswitch.public[count.index].id
  route_table_id = alicloud_route_table.public.id
}

resource "alicloud_route_table_attachment" "private" {
  count = 2

  vswitch_id     = alicloud_vswitch.private[count.index].id
  route_table_id = alicloud_route_table.private[count.index].id
}

# 安全组
resource "alicloud_security_group" "main" {
  name        = "${var.project_name}-${var.environment}-sg"
  vpc_id      = alicloud_vpc.main.id
  description = "Security group for ${var.project_name} ${var.environment} environment"

  tags = {
    Name        = "${var.project_name}-${var.environment}-sg"
    Environment = var.environment
  }
}

resource "alicloud_security_group_rule" "allow_http" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "80/80"
  priority          = 1
  security_group_id = alicloud_security_group.main.id
  cidr_ip           = "0.0.0.0/0"
}

resource "alicloud_security_group_rule" "allow_https" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "443/443"
  priority          = 1
  security_group_id = alicloud_security_group.main.id
  cidr_ip           = "0.0.0.0/0"
}

resource "alicloud_security_group_rule" "allow_all_egress" {
  type              = "egress"
  ip_protocol       = "all"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "-1/-1"
  priority          = 1
  security_group_id = alicloud_security_group.main.id
  cidr_ip           = "0.0.0.0/0"
}

