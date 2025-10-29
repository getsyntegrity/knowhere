# VPC和网络配置

# 创建VPC（如果不使用现有VPC）
resource "alicloud_vpc" "main" {
  count      = var.use_existing_vpc ? 0 : 1
  vpc_name   = "${var.project_name}-${var.environment}-vpc"
  cidr_block = "10.0.0.0/16"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-vpc"
  })
}

# 交换机 - 公共子网
resource "alicloud_vswitch" "public" {
  count        = var.use_existing_vpc ? 0 : 2
  vpc_id       = alicloud_vpc.main[0].id
  cidr_block   = "10.0.${count.index + 1}.0/24"
  zone_id      = data.alicloud_zones.available.zones[count.index].id
  vswitch_name = "${var.project_name}-${var.environment}-public-vswitch-${count.index + 1}"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-public-vswitch-${count.index + 1}"
    Type = "Public"
  })
}

# 交换机 - 私有子网（用于数据库）
resource "alicloud_vswitch" "private" {
  count        = var.use_existing_vpc ? 0 : 2
  vpc_id       = alicloud_vpc.main[0].id
  cidr_block   = "10.0.${count.index + 10}.0/24"
  zone_id      = data.alicloud_zones.available.zones[count.index].id
  vswitch_name = "${var.project_name}-${var.environment}-private-vswitch-${count.index + 1}"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-private-vswitch-${count.index + 1}"
    Type = "Private"
  })
}

# NAT网关（用于私有子网访问外网）
resource "alicloud_nat_gateway" "main" {
  count            = var.use_existing_vpc ? 0 : 1
  nat_gateway_name = "${var.project_name}-${var.environment}-nat"
  vpc_id           = alicloud_vpc.main[0].id
  payment_type     = "PayAsYouGo"
  nat_type         = "Enhanced"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-nat-gateway"
  })
}

# EIP for NAT Gateway
resource "alicloud_eip_address" "nat" {
  count                = var.use_existing_vpc ? 0 : 1
  address_name         = "${var.project_name}-${var.environment}-nat-eip"
  bandwidth            = "100"
  internet_charge_type = "PayByBandwidth"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-nat-eip"
  })
}

# 绑定EIP到NAT Gateway
resource "alicloud_eip_association" "nat" {
  count         = var.use_existing_vpc ? 0 : 1
  allocation_id = alicloud_eip_address.nat[0].id
  instance_id   = alicloud_nat_gateway.main[0].id
}

# 路由表 - 公共路由表
resource "alicloud_route_table" "public" {
  count            = var.use_existing_vpc ? 0 : 1
  vpc_id           = alicloud_vpc.main[0].id
  route_table_name = "${var.project_name}-${var.environment}-public-rt"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-public-rt"
  })
}

# 添加默认路由到Internet（公共子网通过NAT网关）
resource "alicloud_route_entry" "public_default" {
  count                   = var.use_existing_vpc ? 0 : 1
  route_table_id          = alicloud_route_table.public[0].id
  destination_cidrblock   = "0.0.0.0/0"
  nexthop_type            = "NatGateway"
  nexthop_id              = alicloud_nat_gateway.main[0].id
}

# 路由表 - 私有路由表
resource "alicloud_route_table" "private" {
  count            = var.use_existing_vpc ? 0 : 2
  vpc_id           = alicloud_vpc.main[0].id
  route_table_name = "${var.project_name}-${var.environment}-private-rt-${count.index + 1}"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-private-rt-${count.index + 1}"
  })
}

# 添加默认路由到NAT网关
resource "alicloud_route_entry" "private_default" {
  count                 = var.use_existing_vpc ? 0 : 2
  route_table_id        = alicloud_route_table.private[count.index].id
  destination_cidrblock = "0.0.0.0/0"
  nexthop_type          = "NatGateway"
  nexthop_id            = alicloud_nat_gateway.main[0].id
}

# 路由表关联
resource "alicloud_route_table_attachment" "public" {
  count          = var.use_existing_vpc ? 0 : 2
  vswitch_id     = alicloud_vswitch.public[count.index].id
  route_table_id = alicloud_route_table.public[0].id
}

resource "alicloud_route_table_attachment" "private" {
  count          = var.use_existing_vpc ? 0 : 2
  vswitch_id     = alicloud_vswitch.private[count.index].id
  route_table_id = alicloud_route_table.private[count.index].id
}
