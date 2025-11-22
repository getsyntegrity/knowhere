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

# ============================================================================
# 用户验证和Webhook配置 Secrets
# ============================================================================

# Users Verify Token Secret
resource "aws_secretsmanager_secret" "users_verify_token_secret" {
  name        = "knowhere/${var.environment}/users-verify-token-secret"
  description = "用户验证令牌密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-users-verify-token-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "users_verify_token_secret" {
  secret_id     = aws_secretsmanager_secret.users_verify_token_secret.id
  secret_string = var.users_verify_token_secret != "" ? var.users_verify_token_secret : ""
}

# Users Reset Password Token Secret
resource "aws_secretsmanager_secret" "users_reset_password_token_secret" {
  name        = "knowhere/${var.environment}/users-reset-password-token-secret"
  description = "用户重置密码令牌密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-users-reset-password-token-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "users_reset_password_token_secret" {
  secret_id     = aws_secretsmanager_secret.users_reset_password_token_secret.id
  secret_string = var.users_reset_password_token_secret != "" ? var.users_reset_password_token_secret : ""
}

# Webhook Signing Secret
resource "aws_secretsmanager_secret" "webhook_signing_secret" {
  name        = "knowhere/${var.environment}/webhook-signing-secret"
  description = "Webhook签名密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-webhook-signing-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "webhook_signing_secret" {
  secret_id     = aws_secretsmanager_secret.webhook_signing_secret.id
  secret_string = var.webhook_signing_secret != "" ? var.webhook_signing_secret : ""
}

# S3 Webhook Auth Token
resource "aws_secretsmanager_secret" "s3_webhook_auth_token" {
  name        = "knowhere/${var.environment}/s3-webhook-auth-token"
  description = "S3/MinIO Webhook认证令牌"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-s3-webhook-auth-token"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "s3_webhook_auth_token" {
  secret_id     = aws_secretsmanager_secret.s3_webhook_auth_token.id
  secret_string = var.s3_webhook_auth_token != "" ? var.s3_webhook_auth_token : ""
}

# Stripe Webhook Secret
resource "aws_secretsmanager_secret" "stripe_webhook_secret" {
  name        = "knowhere/${var.environment}/stripe-webhook-secret"
  description = "Stripe Webhook密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-stripe-webhook-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "stripe_webhook_secret" {
  secret_id     = aws_secretsmanager_secret.stripe_webhook_secret.id
  secret_string = var.stripe_webhook_secret != "" ? var.stripe_webhook_secret : "not-set"
}

# ============================================================================
# 第三方服务配置 Secrets
# ============================================================================

# Resend API Key
resource "aws_secretsmanager_secret" "resend_api_key" {
  name        = "knowhere/${var.environment}/resend-api-key"
  description = "Resend邮件API密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-resend-api-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "resend_api_key" {
  secret_id     = aws_secretsmanager_secret.resend_api_key.id
  secret_string = var.resend_api_key != "" ? var.resend_api_key : "not-set"
}

# Moesif Application ID
resource "aws_secretsmanager_secret" "moesif_application_id" {
  name        = "knowhere/${var.environment}/moesif-application-id"
  description = "Moesif应用ID"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-moesif-application-id-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "moesif_application_id" {
  secret_id     = aws_secretsmanager_secret.moesif_application_id.id
  secret_string = var.moesif_application_id != "" ? var.moesif_application_id : "not-set"
}

# ============================================================================
# OAuth配置 Secrets
# ============================================================================

# Google OAuth
resource "aws_secretsmanager_secret" "google_client_id" {
  name        = "knowhere/${var.environment}/google-client-id"
  description = "Google OAuth客户端ID"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-google-client-id-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "google_client_id" {
  secret_id     = aws_secretsmanager_secret.google_client_id.id
  secret_string = var.google_client_id != "" ? var.google_client_id : "not-set"
}

resource "aws_secretsmanager_secret" "google_client_secret" {
  name        = "knowhere/${var.environment}/google-client-secret"
  description = "Google OAuth客户端密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-google-client-secret-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "google_client_secret" {
  secret_id     = aws_secretsmanager_secret.google_client_secret.id
  secret_string = var.google_client_secret != "" ? var.google_client_secret : "not-set"
}

# GitHub OAuth
resource "aws_secretsmanager_secret" "github_client_id" {
  name        = "knowhere/${var.environment}/github-client-id"
  description = "GitHub OAuth客户端ID"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-github-client-id-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "github_client_id" {
  secret_id     = aws_secretsmanager_secret.github_client_id.id
  secret_string = var.github_client_id != "" ? var.github_client_id : "not-set"
}

resource "aws_secretsmanager_secret" "github_client_secret" {
  name        = "knowhere/${var.environment}/github-client-secret"
  description = "GitHub OAuth客户端密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-github-client-secret-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "github_client_secret" {
  secret_id     = aws_secretsmanager_secret.github_client_secret.id
  secret_string = var.github_client_secret != "" ? var.github_client_secret : "not-set"
}

# Apple OAuth
resource "aws_secretsmanager_secret" "apple_client_id" {
  name        = "knowhere/${var.environment}/apple-client-id"
  description = "Apple OAuth客户端ID"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-apple-client-id-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "apple_client_id" {
  secret_id     = aws_secretsmanager_secret.apple_client_id.id
  secret_string = var.apple_client_id != "" ? var.apple_client_id : "not-set"
}

resource "aws_secretsmanager_secret" "apple_client_secret" {
  name        = "knowhere/${var.environment}/apple-client-secret"
  description = "Apple OAuth客户端密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-apple-client-secret-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "apple_client_secret" {
  secret_id     = aws_secretsmanager_secret.apple_client_secret.id
  secret_string = var.apple_client_secret != "" ? var.apple_client_secret : "not-set"
}

# ============================================================================
# 邮件配置 Secrets
# ============================================================================

# SMTP Password
resource "aws_secretsmanager_secret" "smtp_password" {
  name        = "knowhere/${var.environment}/smtp-password"
  description = "SMTP密码"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-smtp-password-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "smtp_password" {
  secret_id     = aws_secretsmanager_secret.smtp_password.id
  secret_string = var.smtp_password != "" ? var.smtp_password : "not-set"
}

# ============================================================================
# AI模型配置 Secrets
# ============================================================================

# DeepSeek API Key
resource "aws_secretsmanager_secret" "ds_key" {
  name        = "knowhere/${var.environment}/ds-key"
  description = "DeepSeek API密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-ds-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "ds_key" {
  secret_id     = aws_secretsmanager_secret.ds_key.id
  secret_string = var.ds_key != "" ? var.ds_key : "not-set"
}

# 阿里云 API Key
resource "aws_secretsmanager_secret" "ali_api_key" {
  name        = "knowhere/${var.environment}/ali-api-key"
  description = "阿里云API密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-ali-api-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "ali_api_key" {
  secret_id     = aws_secretsmanager_secret.ali_api_key.id
  secret_string = var.ali_api_key != "" ? var.ali_api_key : "not-set"
}

# 火山引擎 API Key
resource "aws_secretsmanager_secret" "ark_api_key" {
  name        = "knowhere/${var.environment}/ark-api-key"
  description = "火山引擎API密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-ark-api-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "ark_api_key" {
  secret_id     = aws_secretsmanager_secret.ark_api_key.id
  secret_string = var.ark_api_key != "" ? var.ark_api_key : "not-set"
}

# OpenAI API Key
resource "aws_secretsmanager_secret" "gpt_api_key" {
  name        = "knowhere/${var.environment}/gpt-api-key"
  description = "OpenAI API密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-gpt-api-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "gpt_api_key" {
  secret_id     = aws_secretsmanager_secret.gpt_api_key.id
  secret_string = var.gpt_api_key != "" ? var.gpt_api_key : "not-set"
}

# MinerU API Key
resource "aws_secretsmanager_secret" "mineru_api_key" {
  name        = "knowhere/${var.environment}/mineru-api-key"
  description = "MinerU API密钥"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-mineru-api-key-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "mineru_api_key" {
  secret_id     = aws_secretsmanager_secret.mineru_api_key.id
  secret_string = var.mineru_api_key != "" ? var.mineru_api_key : "not-set"
}

# ============================================================================
# Celery配置 Secrets
# ============================================================================

# Celery Broker URL (从 RabbitMQ 配置构建)
resource "aws_secretsmanager_secret" "celery_broker_url" {
  name        = "knowhere/${var.environment}/celery-broker-url"
  description = "Celery Broker URL"
  kms_key_id  = aws_kms_key.secrets.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-celery-broker-url-secret"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "celery_broker_url" {
  secret_id = aws_secretsmanager_secret.celery_broker_url.id
  # 从 RabbitMQ 配置构建 Celery Broker URL
  # 注意：RabbitMQ endpoint 需要通过 aws_mq_broker 资源获取
  # endpoints[0] 返回 amqps://host:5671，需要提取 host 部分
  secret_string = "amqps://${var.mq_username}:${var.mq_password}@${replace(replace(aws_mq_broker.rabbitmq.instances[0].endpoints[0], "amqps://", ""), ":5671", "")}:5671//"
}

