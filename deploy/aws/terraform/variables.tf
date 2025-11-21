# Terraform变量定义 - AWS部署
# 所有变量集中定义在此文件中

# ============================================================================
# 基础配置变量
# ============================================================================

variable "aws_region" {
  description = "AWS区域"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "环境名称（Terraform 仅用于 prod 环境，dev/test 环境使用 Docker Compose）"
  type        = string
  default     = "prod"
  
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod. Note: Terraform is only used for prod environment. Use Docker Compose for dev/test environments."
  }
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "knowhere"
}

variable "domain_name" {
  description = "域名"
  type        = string
}

variable "app_version" {
  description = "应用版本号（从Git Tag或commit hash获取）"
  type        = string
  default     = "dev"
}

variable "api_webhook_endpoint" {
  description = "API webhook endpoint for S3 events (SNS subscription)"
  type        = string
  default     = ""
}

variable "use_route53" {
  description = "是否使用Route53管理DNS记录。如果为false，需要在外部DNS提供商手动配置DNS记录"
  type        = bool
  default     = false
}

# ============================================================================
# 数据库配置变量
# ============================================================================

variable "db_password" {
  description = "数据库密码"
  type        = string
  sensitive   = true
}

# ============================================================================
# RabbitMQ配置变量
# ============================================================================

variable "mq_username" {
  description = "Amazon MQ RabbitMQ用户名"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "mq_password" {
  description = "Amazon MQ RabbitMQ密码"
  type        = string
  sensitive   = true
}

# ============================================================================
# Secrets Manager配置变量（敏感信息）
# ============================================================================

variable "s3_access_key_id" {
  description = "S3访问密钥ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "s3_secret_access_key" {
  description = "S3秘密访问密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "app_secret_key" {
  description = "应用JWT密钥（用于签名token）"
  type        = string
  sensitive   = true
  default     = ""
}

variable "stripe_secret_key" {
  description = "Stripe密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "stripe_publishable_key" {
  description = "Stripe发布密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "posthog_key" {
  description = "PostHog密钥"
  type        = string
  sensitive   = true
  default     = ""
}

