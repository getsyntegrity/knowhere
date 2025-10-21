# 安全组配置

# 应用服务器安全组
resource "aws_security_group" "app_server" {
  count       = var.use_existing_security_group ? 0 : 1
  name        = "${var.project_name}-${var.environment}-app-server-sg"
  description = "安全组 - Knowhere应用服务器"
  vpc_id      = var.use_existing_vpc ? var.existing_vpc_id : aws_vpc.main[0].id

  # HTTP访问
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS访问
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH访问（限制来源IP）
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # 生产环境应该限制到特定IP
  }

  # 应用端口 - Backend API
  ingress {
    description = "Backend API"
    from_port   = 5005
    to_port     = 5005
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # 应用端口 - Web Frontend
  ingress {
    description = "Web Frontend"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # 出站规则 - 所有流量
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-app-server-sg"
  })
}

# 数据库安全组（如果创建新RDS）
resource "aws_security_group" "database" {
  count       = var.use_existing_rds ? 0 : 1
  name        = "${var.project_name}-${var.environment}-database-sg"
  description = "Security group for database"
  vpc_id      = var.use_existing_vpc ? var.existing_vpc_id : aws_vpc.main[0].id

  # PostgreSQL访问
  ingress {
    description     = "PostgreSQL"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.use_existing_security_group ? [var.existing_security_group_id] : [aws_security_group.app_server[0].id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-database-sg"
  })
}

# Redis安全组（如果创建新Redis）
resource "aws_security_group" "redis" {
  count       = var.use_existing_redis ? 0 : 1
  name        = "${var.project_name}-${var.environment}-redis-sg"
  description = "Security group for Redis"
  vpc_id      = var.use_existing_vpc ? var.existing_vpc_id : aws_vpc.main[0].id

  # Redis访问
  ingress {
    description     = "Redis"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.use_existing_security_group ? [var.existing_security_group_id] : [aws_security_group.app_server[0].id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-redis-sg"
  })
}

# 负载均衡器安全组（如果使用ALB）
resource "aws_security_group" "alb" {
  count       = var.use_existing_vpc ? 0 : 1
  name        = "${var.project_name}-${var.environment}-alb-sg"
  description = "安全组 - 应用负载均衡器"
  vpc_id      = aws_vpc.main[0].id

  # HTTP访问
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS访问
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # 出站规则
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-alb-sg"
  })
}
