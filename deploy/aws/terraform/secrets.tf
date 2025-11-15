# Secrets Manager - 应用密钥管理

# KMS密钥 - 用于Secrets Manager加密
resource "aws_kms_key" "secrets" {
  description             = "KMS key for Secrets Manager encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name        = "${var.project_name}-secrets-kms-key"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.project_name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# 变量定义在 variables.tf 中

# DATABASE_URL Secret
resource "aws_secretsmanager_secret" "database_url" {
  name        = "knowhere/${var.environment}/database-url"
  description = "PostgreSQL数据库连接URL"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-database-url-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  # 从RDS信息构建DATABASE_URL
  secret_string = "postgresql+asyncpg://${aws_rds_cluster.postgres.master_username}:${var.db_password}@${aws_rds_cluster.postgres.endpoint}:5432/${aws_rds_cluster.postgres.database_name}"
}

# S3 Access Key ID Secret
resource "aws_secretsmanager_secret" "s3_access_key" {
  name        = "knowhere/${var.environment}/s3-access-key"
  description = "S3访问密钥ID"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-s3-access-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "s3_access_key" {
  secret_id     = aws_secretsmanager_secret.s3_access_key.id
  secret_string = var.s3_access_key_id != "" ? var.s3_access_key_id : ""  # 如果未提供，使用空字符串，需要后续手动设置
}

# S3 Secret Access Key Secret
resource "aws_secretsmanager_secret" "s3_secret_key" {
  name        = "knowhere/${var.environment}/s3-secret-key"
  description = "S3秘密访问密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-s3-secret-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "s3_secret_key" {
  secret_id     = aws_secretsmanager_secret.s3_secret_key.id
  secret_string = var.s3_secret_access_key != "" ? var.s3_secret_access_key : ""  # 如果未提供，使用空字符串，需要后续手动设置
}

# Application Secret Key Secret
resource "aws_secretsmanager_secret" "secret_key" {
  name        = "knowhere/${var.environment}/secret-key"
  description = "应用JWT密钥（用于签名token）"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-secret-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "secret_key" {
  secret_id     = aws_secretsmanager_secret.secret_key.id
  secret_string = var.app_secret_key != "" ? var.app_secret_key : ""  # 如果未提供，使用空字符串，需要后续手动设置
}

# Stripe Secret Key Secret
resource "aws_secretsmanager_secret" "stripe_secret_key" {
  name        = "knowhere/${var.environment}/stripe-secret-key"
  description = "Stripe密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-stripe-secret-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "stripe_secret_key" {
  secret_id     = aws_secretsmanager_secret.stripe_secret_key.id
  secret_string = var.stripe_secret_key != "" ? var.stripe_secret_key : "not-set"  # 如果未提供，使用默认值，需要后续手动设置
}

# Stripe Publishable Key Secret
resource "aws_secretsmanager_secret" "stripe_publishable_key" {
  name        = "knowhere/${var.environment}/stripe-publishable-key"
  description = "Stripe发布密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-stripe-publishable-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "stripe_publishable_key" {
  secret_id     = aws_secretsmanager_secret.stripe_publishable_key.id
  secret_string = var.stripe_publishable_key != "" ? var.stripe_publishable_key : "not-set"  # 如果未提供，使用默认值，需要后续手动设置
}

# PostHog Key Secret
resource "aws_secretsmanager_secret" "posthog_key" {
  name        = "knowhere/${var.environment}/posthog-key"
  description = "PostHog密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-posthog-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "posthog_key" {
  secret_id     = aws_secretsmanager_secret.posthog_key.id
  secret_string = var.posthog_key != "" ? var.posthog_key : "not-set"  # 如果未提供，使用默认值，需要后续手动设置
}

