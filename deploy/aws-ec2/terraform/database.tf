# 数据库配置

# RDS PostgreSQL实例（如果不使用现有RDS）
resource "aws_db_instance" "main" {
  count = var.use_existing_rds ? 0 : 1

  identifier = "${var.project_name}-${var.environment}-db"

  # 引擎配置
  engine         = "postgres"
  engine_version = "15.7"
  instance_class = "db.t3.micro" # 测试环境使用最小实例

  # 存储配置
  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp2"
  storage_encrypted     = true

  # 数据库配置
  db_name  = "knowhere"
  username = "postgres"
  password = random_password.db_password[0].result
  port     = 5432

  # 网络配置
  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  vpc_security_group_ids = [aws_security_group.database[0].id]
  publicly_accessible    = false

  # 备份配置
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"
  skip_final_snapshot     = true # 测试环境跳过最终快照

  # 监控配置
  monitoring_interval          = 0 # 测试环境不启用增强监控
  performance_insights_enabled = false

  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-db"
  })

  depends_on = [aws_db_subnet_group.main]
}

# 数据库密码
resource "random_password" "db_password" {
  count = var.use_existing_rds ? 0 : 1

  length  = 16
  special = true
}

# ElastiCache Redis集群（如果不使用现有Redis）
resource "aws_elasticache_replication_group" "main" {
  count = var.use_existing_redis ? 0 : 1

  replication_group_id = "${var.project_name}-${var.environment}-redis"
  description          = "Redis cluster for Knowhere"

  # 节点配置
  node_type            = "cache.t3.micro" # 测试环境使用最小实例
  port                 = 6379
  parameter_group_name = "default.redis7"

  # 集群配置
  num_cache_clusters = 1 # 测试环境单节点
  engine_version     = "7.0"

  # 网络配置
  subnet_group_name  = aws_elasticache_subnet_group.main[0].name
  security_group_ids = [aws_security_group.redis[0].id]

  # 备份配置
  snapshot_retention_limit = 1
  snapshot_window          = "03:00-04:00"

  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-redis"
  })

  depends_on = [aws_elasticache_subnet_group.main]
}

# S3存储桶（如果不使用现有S3）
resource "aws_s3_bucket" "main" {
  count = var.use_existing_s3 ? 0 : 1

  bucket = "${var.project_name}-${var.environment}-storage-${random_string.bucket_suffix[0].result}"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-storage"
  })
}

# S3存储桶版本控制
resource "aws_s3_bucket_versioning" "main" {
  count = var.use_existing_s3 ? 0 : 1

  bucket = aws_s3_bucket.main[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3存储桶加密
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  count = var.use_existing_s3 ? 0 : 1

  bucket = aws_s3_bucket.main[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3存储桶公共访问阻止
resource "aws_s3_bucket_public_access_block" "main" {
  count = var.use_existing_s3 ? 0 : 1

  bucket = aws_s3_bucket.main[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3存储桶生命周期配置
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  count = var.use_existing_s3 ? 0 : 1

  bucket = aws_s3_bucket.main[0].id

  rule {
    id     = "delete_old_versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# 随机字符串用于S3存储桶名称唯一性
resource "random_string" "bucket_suffix" {
  count = var.use_existing_s3 ? 0 : 1

  length  = 8
  special = false
  upper   = false
}

# 将数据库密码存储到Secrets Manager
resource "aws_secretsmanager_secret" "db_password" {
  count = var.use_existing_rds ? 0 : 1

  name                    = "${var.project_name}/${var.environment}/database-password-new"
  description             = "Database password for Knowhere"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "db_password" {
  count = var.use_existing_rds ? 0 : 1

  secret_id = aws_secretsmanager_secret.db_password[0].id
  secret_string = jsonencode({
    username = "postgres"
    password = random_password.db_password[0].result
    host     = aws_db_instance.main[0].endpoint
    port     = 5432
    database = "knowhere"
  })
}

# 将Redis密码存储到Secrets Manager
resource "aws_secretsmanager_secret" "redis_password" {
  count = var.use_existing_redis ? 0 : 1

  name                    = "${var.project_name}/${var.environment}/redis-password"
  description             = "Redis password for Knowhere"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "redis_password" {
  count = var.use_existing_redis ? 0 : 1

  secret_id = aws_secretsmanager_secret.redis_password[0].id
  secret_string = jsonencode({
    host     = aws_elasticache_replication_group.main[0].primary_endpoint_address
    port     = 6379
    password = "" # Redis默认无密码
  })
}
