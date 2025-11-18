# Terraform变量定义 - 阿里云部署
# 所有变量集中定义在此文件中

# ============================================================================
# 基础配置变量
# ============================================================================

variable "region" {
  description = "阿里云区域"
  type        = string
  default     = "cn-guangzhou"
}

variable "access_key" {
  description = "阿里云AccessKey ID"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "阿里云AccessKey Secret"
  type        = string
  sensitive   = true
}

# 主账号凭证（用于处理需要更高权限的资源，如 ACK 集群）
variable "master_access_key" {
  description = "阿里云主账号AccessKey ID（用于ACK等需要高权限的资源）"
  type        = string
  sensitive   = true
  default     = ""
}

variable "master_secret_key" {
  description = "阿里云主账号AccessKey Secret（用于ACK等需要高权限的资源）"
  type        = string
  sensitive   = true
  default     = ""
}

variable "environment" {
  description = "环境名称 (dev/test/prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod"
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
  description = "API webhook endpoint for OSS events"
  type        = string
  default     = ""
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

variable "rabbitmq_username" {
  description = "RabbitMQ用户名"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "rabbitmq_password" {
  description = "RabbitMQ密码"
  type        = string
  sensitive   = true
}

# ============================================================================
# OSS配置变量（敏感信息）
# ============================================================================

variable "oss_access_key_id" {
  description = "OSS访问密钥ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oss_secret_access_key" {
  description = "OSS秘密访问密钥"
  type        = string
  sensitive   = true
  default     = ""
}

# ============================================================================
# 应用配置变量（敏感信息）
# ============================================================================

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

