# KMS密钥 - 用于RDS加密
resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name        = "${var.project_name}-rds-kms-key"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.project_name}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# 数据库配置
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name        = "${var.project_name}-${var.environment}-db-subnet-group"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RDS Serverless v2集群
resource "aws_rds_cluster" "postgres" {
  cluster_identifier = "${var.project_name}-${var.environment}-postgres-cluster"

  engine         = "aurora-postgresql"
  engine_version = "15.4"
  engine_mode    = "provisioned"

  database_name   = "knowhere"
  master_username = "postgres"
  master_password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Serverless v2配置
  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 16.0
  }

  # 备份配置
  backup_retention_period = 30
  preferred_backup_window = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"

  # 加密配置
  storage_encrypted = true
  kms_key_id       = aws_kms_key.rds.arn

  # 启用性能洞察
  enabled_cloudwatch_logs_exports = ["postgresql"]

  # 删除保护
  deletion_protection = var.environment == "prod" ? true : false
  skip_final_snapshot = var.environment != "prod"

  tags = {
    Name        = "${var.project_name}-${var.environment}-postgres-cluster"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RDS Serverless v2实例
resource "aws_rds_cluster_instance" "postgres" {
  count = var.environment == "prod" ? 2 : 1

  identifier         = "${var.project_name}-${var.environment}-postgres-${count.index + 1}"
  cluster_identifier = aws_rds_cluster.postgres.id
  instance_class     = "db.serverless"

  engine         = aws_rds_cluster.postgres.engine
  engine_version = aws_rds_cluster.postgres.engine_version

  performance_insights_enabled = true
  performance_insights_kms_key_id = aws_kms_key.rds.arn
  performance_insights_retention_period = 7

  tags = {
    Name        = "${var.project_name}-${var.environment}-postgres-instance-${count.index + 1}"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ElastiCache Serverless Redis
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-cache-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name        = "${var.project_name}-${var.environment}-cache-subnet"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ElastiCache Serverless缓存
resource "aws_elasticache_serverless_cache" "redis" {
  engine = "redis"
  name   = "${var.project_name}-${var.environment}-redis-serverless"

  cache_usage_limits {
    data_storage {
      maximum = 5
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 5000
    }
  }

  daily_snapshot_time      = "03:00"
  description              = "Serverless Redis cache for ${var.project_name}"
  kms_key_id               = aws_kms_key.rds.arn
  major_engine_version     = "7"
  security_group_ids       = [aws_security_group.elasticache.id]
  snapshot_retention_limit = 7
  subnet_ids               = aws_subnet.private[*].id

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-serverless"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Secrets Manager - 存储Redis连接信息
resource "aws_secretsmanager_secret" "redis_host" {
  name        = "knowhere/${var.environment}/redis-host"
  description = "ElastiCache Serverless Redis endpoint"

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-host-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "redis_host" {
  secret_id     = aws_secretsmanager_secret.redis_host.id
  secret_string = aws_elasticache_serverless_cache.redis.endpoint[0].address  # 直接存储host字符串
}

# Redis端口Secret
resource "aws_secretsmanager_secret" "redis_port" {
  name        = "knowhere/${var.environment}/redis-port"
  description = "ElastiCache Serverless Redis port"

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-port-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "redis_port" {
  secret_id     = aws_secretsmanager_secret.redis_port.id
  secret_string = tostring(aws_elasticache_serverless_cache.redis.endpoint[0].port)  # 直接存储port字符串
}

resource "aws_secretsmanager_secret" "redis_password" {
  name        = "knowhere/${var.environment}/redis-password"
  description = "ElastiCache Serverless Redis password (if required)"

  tags = {
    Name        = "${var.project_name}-${var.environment}-redis-password-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "redis_password" {
  secret_id     = aws_secretsmanager_secret.redis_password.id
  secret_string = ""  # ElastiCache Serverless默认不需要密码，但保留secret以备将来使用
}

# RDS监控角色
resource "aws_iam_role" "rds_monitoring" {
  name = "${var.project_name}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# 变量
variable "db_password" {
  description = "数据库密码"
  type        = string
  sensitive   = true
}
