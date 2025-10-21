# VPC和网络配置

# 创建VPC（如果不使用现有VPC）
resource "aws_vpc" "main" {
  count                = var.use_existing_vpc ? 0 : 1
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-vpc"
  })
}

# 互联网网关
resource "aws_internet_gateway" "main" {
  count  = var.use_existing_vpc ? 0 : 1
  vpc_id = aws_vpc.main[0].id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-igw"
  })
}

# 公共子网
resource "aws_subnet" "public" {
  count = var.use_existing_vpc ? 0 : 2

  vpc_id                  = aws_vpc.main[0].id
  cidr_block              = "10.0.${count.index + 1}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-public-subnet-${count.index + 1}"
    Type = "Public"
  })
}

# 私有子网（用于数据库）
resource "aws_subnet" "private" {
  count = var.use_existing_vpc ? 0 : 2

  vpc_id            = aws_vpc.main[0].id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-private-subnet-${count.index + 1}"
    Type = "Private"
  })
}

# NAT网关（用于私有子网）
resource "aws_eip" "nat" {
  count = var.use_existing_vpc ? 0 : 2

  domain     = "vpc"
  depends_on = [aws_internet_gateway.main]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-nat-eip-${count.index + 1}"
  })
}

resource "aws_nat_gateway" "main" {
  count = var.use_existing_vpc ? 0 : 2

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-nat-gateway-${count.index + 1}"
  })

  depends_on = [aws_internet_gateway.main]
}

# 路由表
resource "aws_route_table" "public" {
  count  = var.use_existing_vpc ? 0 : 1
  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-public-rt"
  })
}

resource "aws_route_table" "private" {
  count = var.use_existing_vpc ? 0 : 2

  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-private-rt-${count.index + 1}"
  })
}

# 路由表关联
resource "aws_route_table_association" "public" {
  count = var.use_existing_vpc ? 0 : 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_route_table_association" "private" {
  count = var.use_existing_vpc ? 0 : 2

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# 数据库子网组
resource "aws_db_subnet_group" "main" {
  count = var.use_existing_rds ? 0 : 1

  name       = "${var.project_name}-${var.environment}-db-subnet-group"
  subnet_ids = var.use_existing_vpc ? data.aws_subnets.existing[0].ids : aws_subnet.private[*].id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  })
}

# ElastiCache子网组
resource "aws_elasticache_subnet_group" "main" {
  count = var.use_existing_redis ? 0 : 1

  name       = "${var.project_name}-${var.environment}-cache-subnet-group"
  subnet_ids = var.use_existing_vpc ? data.aws_subnets.existing[0].ids : aws_subnet.private[*].id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-cache-subnet-group"
  })
}
