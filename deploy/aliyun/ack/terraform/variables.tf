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
  description = "环境名称（Terraform 仅用于 prod 环境，dev/test 环境使用 Docker Compose）"
  type        = string
  default     = "prod"
  
  validation {
    condition     = var.environment == "prod"
    error_message = "Environment must be 'prod'. Terraform is only used for prod environment. Use Docker Compose for dev/test environments."
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

# ============================================================================
# 存储配置变量
# ============================================================================

variable "s3_type" {
  description = "存储类型: s3 (AWS S3), oss (阿里云OSS), minio (MinIO)"
  type        = string
  default     = "oss"
}

variable "s3_region" {
  description = "S3/OSS区域"
  type        = string
  default     = "cn-guangzhou"
}

variable "s3_use_ssl" {
  description = "是否使用SSL"
  type        = bool
  default     = true
}

variable "s3_addressing_style" {
  description = "S3寻址风格: auto, path, virtual"
  type        = string
  default     = "auto"
}

variable "oss_endpoint" {
  description = "OSS endpoint（仅S3_TYPE=oss时需要）"
  type        = string
  default     = ""
}

variable "s3_private_domain" {
  description = "S3私有域名"
  type        = string
  default     = ""
}

variable "s3_temp_path" {
  description = "S3临时路径"
  type        = string
  default     = "/tmp"
}

# ============================================================================
# 数据库SSL配置变量
# ============================================================================

variable "db_ssl_mode" {
  description = "数据库SSL模式: disable, allow, prefer, require, verify-ca, verify-full"
  type        = string
  default     = "prefer"
}

# ============================================================================
# Redis配置变量
# ============================================================================

variable "redis_password" {
  description = "Redis密码（如果为空则不需要密码）"
  type        = string
  sensitive   = true
  default     = ""
}

variable "redis_database" {
  description = "Redis数据库编号"
  type        = number
  default     = 0
}

# ============================================================================
# Celery配置变量
# ============================================================================

variable "message_broker_type" {
  description = "消息代理类型: rabbitmq"
  type        = string
  default     = "rabbitmq"
}

variable "celery_result_backend" {
  description = "Celery结果后端: rpc:// 或 redis://"
  type        = string
  default     = "rpc://"
}

# ============================================================================
# 应用配置变量（非敏感）
# ============================================================================

variable "app_title" {
  description = "应用标题"
  type        = string
  default     = "Konwhere AI知识库管理系统"
}

variable "app_description" {
  description = "应用描述"
  type        = string
  default     = "基于AI的知识库管理和智能问答系统"
}

variable "tmp_path" {
  description = "临时文件路径"
  type        = string
  default     = "/tmp/aismart_bid"
}

variable "font_path" {
  description = "字体文件路径"
  type        = string
  default     = "/usr/share/fonts"
}

variable "chromedriver_path" {
  description = "ChromeDriver路径"
  type        = string
  default     = "/usr/bin/chromedriver"
}

variable "algorithm" {
  description = "JWT算法"
  type        = string
  default     = "HS256"
}

variable "access_token_expire_minutes" {
  description = "访问令牌过期时间（分钟）"
  type        = number
  default     = 10080
}

variable "log_level" {
  description = "日志级别"
  type        = string
  default     = "INFO"
}

variable "debug" {
  description = "是否启用调试模式"
  type        = bool
  default     = false
}

# ============================================================================
# 安全配置变量（敏感信息）
# ============================================================================

variable "users_verify_token_secret" {
  description = "用户验证令牌密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "users_reset_password_token_secret" {
  description = "用户重置密码令牌密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "webhook_signing_secret" {
  description = "Webhook签名密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "s3_webhook_auth_token" {
  description = "S3/MinIO Webhook认证令牌"
  type        = string
  sensitive   = true
  default     = ""
}

variable "sns_signature_verification" {
  description = "是否启用SNS签名验证"
  type        = bool
  default     = true
}

variable "oss_event_callback_key" {
  description = "OSS事件回调密钥（仅S3_TYPE=oss时需要）"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oss_event_verify_signature" {
  description = "是否启用OSS事件签名验证"
  type        = bool
  default     = true
}

# ============================================================================
# 第三方服务配置变量（敏感信息）
# ============================================================================

variable "resend_api_key" {
  description = "Resend邮件API密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "moesif_application_id" {
  description = "Moesif应用ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "stripe_webhook_secret" {
  description = "Stripe Webhook密钥"
  type        = string
  sensitive   = true
  default     = ""
}

# ============================================================================
# OAuth配置变量（敏感信息）
# ============================================================================

variable "google_client_id" {
  description = "Google OAuth客户端ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth客户端密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_client_id" {
  description = "GitHub OAuth客户端ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_client_secret" {
  description = "GitHub OAuth客户端密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "apple_client_id" {
  description = "Apple OAuth客户端ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "apple_client_secret" {
  description = "Apple OAuth客户端密钥"
  type        = string
  sensitive   = true
  default     = ""
}

# ============================================================================
# 邮件配置变量
# ============================================================================

variable "smtp_host" {
  description = "SMTP服务器地址"
  type        = string
  default     = "smtp.gmail.com"
}

variable "smtp_port" {
  description = "SMTP服务器端口"
  type        = number
  default     = 587
}

variable "smtp_user" {
  description = "SMTP用户名"
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "SMTP密码"
  type        = string
  sensitive   = true
  default     = ""
}

variable "emails_from_email" {
  description = "发件人邮箱地址"
  type        = string
  default     = ""
}

variable "emails_from_name" {
  description = "发件人名称"
  type        = string
  default     = "AI Smart Bid"
}

# ============================================================================
# AI模型配置变量（敏感信息）
# ============================================================================

variable "ds_key" {
  description = "DeepSeek API密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ds_url" {
  description = "DeepSeek API URL"
  type        = string
  default     = "https://api.deepseek.com/v1/chat/completions"
}

variable "ali_api_key" {
  description = "阿里云API密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ali_url" {
  description = "阿里云API URL"
  type        = string
  default     = "https://dashscope.aliyuncs.com/compatible-mode/v1"
}

variable "ark_api_key" {
  description = "火山引擎API密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ark_url" {
  description = "火山引擎API URL"
  type        = string
  default     = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
}

variable "gpt_api_key" {
  description = "OpenAI API密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "embedding_model" {
  description = "嵌入模型名称"
  type        = string
  default     = "text-embedding-v1"
}

variable "normal_model" {
  description = "普通模型名称"
  type        = string
  default     = "gpt-3.5-turbo"
}

variable "image_model" {
  description = "图像模型名称"
  type        = string
  default     = "gpt-4-vision-preview"
}

variable "mineru_api_key" {
  description = "MinerU API密钥"
  type        = string
  sensitive   = true
  default     = ""
}

variable "mineru_url" {
  description = "MinerU API URL"
  type        = string
  default     = "https://mineru.net"
}

# ============================================================================
# 文件处理配置变量
# ============================================================================

variable "supported_extensions" {
  description = "支持的文件扩展名（逗号分隔）"
  type        = string
  default     = ".doc,.docx,.pdf,.txt,.xls,.xlsx,.csv,.jpg,.png"
}

variable "max_file_size" {
  description = "最大文件大小（字节）"
  type        = number
  default     = 104857600
}

variable "max_image_size" {
  description = "最大图片大小（字节）"
  type        = number
  default     = 10485760
}

# ============================================================================
# 模型参数配置变量
# ============================================================================

variable "min_confidence_threshold" {
  description = "最小置信度阈值"
  type        = number
  default     = 0.05
}

variable "high_iou_threshold" {
  description = "高IOU阈值"
  type        = number
  default     = 0.9
}

variable "default_embedding_dim" {
  description = "默认嵌入维度"
  type        = number
  default     = 1024
}

variable "default_top_k" {
  description = "默认Top K值"
  type        = number
  default     = 5
}

variable "default_batch_size" {
  description = "默认批次大小"
  type        = number
  default     = 32
}

variable "default_epochs" {
  description = "默认训练轮数"
  type        = number
  default     = 3
}

variable "default_threshold" {
  description = "默认阈值"
  type        = number
  default     = 0.5
}

# ============================================================================
# 订阅配置变量
# ============================================================================

variable "free_plan_initial_credits" {
  description = "免费计划初始积分"
  type        = number
  default     = 100
}

# ============================================================================
# 用户数据目录配置变量
# ============================================================================

variable "users_data_path" {
  description = "用户数据目录路径（API和Worker共享，必须配置绝对路径）"
  type        = string
  default     = "/opt/knowhere/users"
}

