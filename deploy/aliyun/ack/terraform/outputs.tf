# Terraform输出定义 - 阿里云部署
# 所有输出集中定义在此文件中，用于生成 Kubernetes Secrets 和 ConfigMap

# ============================================================================
# 基础设施输出（已存在，从其他文件移动或引用）
# ============================================================================

# 注意：以下输出已在 database.tf, rabbitmq.tf, oss.tf 等文件中定义
# 这里仅列出引用，实际定义保留在原文件中

# ============================================================================
# 数据库相关输出
# ============================================================================

# 注意：rds_endpoint, rds_port, redis_endpoint, redis_port 已在 database.tf 中定义
# 这里只定义新增的输出

output "database_url" {
  description = "数据库连接URL（敏感信息）"
  value       = "postgresql+asyncpg://postgres:${var.db_password}@${alicloud_db_instance.postgres.connection_string}:${alicloud_db_instance.postgres.port}/knowhere"
  sensitive   = true
}

output "db_ssl_mode" {
  description = "数据库SSL模式"
  value       = var.db_ssl_mode
}

# ============================================================================
# Redis相关输出
# ============================================================================

# 注意：redis_endpoint, redis_port 已在 database.tf 中定义
# 这里定义 redis_host 作为 redis_endpoint 的别名，以及新增的输出

output "redis_host" {
  description = "Redis Serverless端点（redis_endpoint 的别名）"
  value       = alicloud_kvstore_instance.redis.connection_domain
}

output "redis_password" {
  description = "Redis密码（敏感信息）"
  value       = var.redis_password
  sensitive   = true
}

output "redis_database" {
  description = "Redis数据库编号"
  value       = var.redis_database
}

# ============================================================================
# RabbitMQ相关输出
# ============================================================================

# 注意：rabbitmq_instance_id, rabbitmq_endpoint, rabbitmq_username, rabbitmq_virtual_host 已在 rabbitmq.tf 中定义
# 这里只定义新增的输出

output "rabbitmq_password" {
  description = "RabbitMQ密码（敏感信息）"
  value       = var.rabbitmq_password
  sensitive   = true
}

output "rabbitmq_port" {
  description = "RabbitMQ端口"
  value       = 5672
}

output "celery_broker_url" {
  description = "Celery Broker URL（敏感信息）"
  value       = "amqp://${var.rabbitmq_username}:${var.rabbitmq_password}@${alicloud_amqp_instance.rabbitmq.id}:5672//"
  sensitive   = true
}

output "celery_result_backend" {
  description = "Celery结果后端"
  value       = var.celery_result_backend
}

output "message_broker_type" {
  description = "消息代理类型"
  value       = var.message_broker_type
}

# ============================================================================
# OSS相关输出
# ============================================================================

# 注意：oss_bucket_name, oss_bucket_endpoint 已在 oss.tf 中定义
# 这里只定义新增的输出

output "s3_type" {
  description = "存储类型"
  value       = var.s3_type
}

output "s3_bucket_name" {
  description = "S3存储桶名称（与OSS相同）"
  value       = alicloud_oss_bucket.main.bucket
}

output "s3_access_key_id" {
  description = "S3/OSS访问密钥ID（敏感信息）"
  value       = var.oss_access_key_id
  sensitive   = true
}

output "s3_secret_access_key" {
  description = "S3/OSS秘密访问密钥（敏感信息）"
  value       = var.oss_secret_access_key
  sensitive   = true
}

output "s3_endpoint_url" {
  description = "S3/OSS Endpoint URL"
  value       = var.oss_endpoint != "" ? var.oss_endpoint : "https://oss-${var.region}.aliyuncs.com"
}

output "s3_private_domain" {
  description = "S3私有域名"
  value       = var.s3_private_domain != "" ? var.s3_private_domain : "https://${alicloud_oss_bucket.main.bucket}.oss-${var.region}.aliyuncs.com"
}

output "s3_temp_path" {
  description = "S3临时路径"
  value       = var.s3_temp_path
}

output "s3_region" {
  description = "S3/OSS区域"
  value       = var.s3_region
}

output "s3_use_ssl" {
  description = "是否使用SSL"
  value       = var.s3_use_ssl
}

output "s3_addressing_style" {
  description = "S3寻址风格"
  value       = var.s3_addressing_style
}

output "oss_endpoint" {
  description = "OSS endpoint"
  value       = var.oss_endpoint != "" ? var.oss_endpoint : "https://oss-${var.region}.aliyuncs.com"
}

# ============================================================================
# 应用配置输出（敏感信息）
# ============================================================================

output "app_secret_key" {
  description = "应用JWT密钥（敏感信息）"
  value       = var.app_secret_key
  sensitive   = true
}

output "users_verify_token_secret" {
  description = "用户验证令牌密钥（敏感信息）"
  value       = var.users_verify_token_secret
  sensitive   = true
}

output "users_reset_password_token_secret" {
  description = "用户重置密码令牌密钥（敏感信息）"
  value       = var.users_reset_password_token_secret
  sensitive   = true
}

output "webhook_signing_secret" {
  description = "Webhook签名密钥（敏感信息）"
  value       = var.webhook_signing_secret
  sensitive   = true
}

output "s3_webhook_auth_token" {
  description = "S3/MinIO Webhook认证令牌（敏感信息）"
  value       = var.s3_webhook_auth_token
  sensitive   = true
}

output "sns_signature_verification" {
  description = "是否启用SNS签名验证"
  value       = var.sns_signature_verification
}

output "oss_event_callback_key" {
  description = "OSS事件回调密钥（敏感信息）"
  value       = var.oss_event_callback_key
  sensitive   = true
}

output "oss_event_verify_signature" {
  description = "是否启用OSS事件签名验证"
  value       = var.oss_event_verify_signature
}

# ============================================================================
# 第三方服务配置输出（敏感信息）
# ============================================================================

output "stripe_secret_key" {
  description = "Stripe密钥（敏感信息）"
  value       = var.stripe_secret_key
  sensitive   = true
}

output "stripe_publishable_key" {
  description = "Stripe发布密钥（敏感信息）"
  value       = var.stripe_publishable_key
  sensitive   = true
}

output "stripe_webhook_secret" {
  description = "Stripe Webhook密钥（敏感信息）"
  value       = var.stripe_webhook_secret
  sensitive   = true
}

output "posthog_key" {
  description = "PostHog密钥（敏感信息）"
  value       = var.posthog_key
  sensitive   = true
}

output "resend_api_key" {
  description = "Resend邮件API密钥（敏感信息）"
  value       = var.resend_api_key
  sensitive   = true
}

output "moesif_application_id" {
  description = "Moesif应用ID（敏感信息）"
  value       = var.moesif_application_id
  sensitive   = true
}

# ============================================================================
# OAuth配置输出（敏感信息）
# ============================================================================

output "google_client_id" {
  description = "Google OAuth客户端ID（敏感信息）"
  value       = var.google_client_id
  sensitive   = true
}

output "google_client_secret" {
  description = "Google OAuth客户端密钥（敏感信息）"
  value       = var.google_client_secret
  sensitive   = true
}

output "github_client_id" {
  description = "GitHub OAuth客户端ID（敏感信息）"
  value       = var.github_client_id
  sensitive   = true
}

output "github_client_secret" {
  description = "GitHub OAuth客户端密钥（敏感信息）"
  value       = var.github_client_secret
  sensitive   = true
}

output "apple_client_id" {
  description = "Apple OAuth客户端ID（敏感信息）"
  value       = var.apple_client_id
  sensitive   = true
}

output "apple_client_secret" {
  description = "Apple OAuth客户端密钥（敏感信息）"
  value       = var.apple_client_secret
  sensitive   = true
}

# ============================================================================
# 邮件配置输出
# ============================================================================

output "smtp_host" {
  description = "SMTP服务器地址"
  value       = var.smtp_host
}

output "smtp_port" {
  description = "SMTP服务器端口"
  value       = var.smtp_port
}

output "smtp_user" {
  description = "SMTP用户名"
  value       = var.smtp_user
}

output "smtp_password" {
  description = "SMTP密码（敏感信息）"
  value       = var.smtp_password
  sensitive   = true
}

output "emails_from_email" {
  description = "发件人邮箱地址"
  value       = var.emails_from_email
}

output "emails_from_name" {
  description = "发件人名称"
  value       = var.emails_from_name
}

# ============================================================================
# AI模型配置输出（敏感信息）
# ============================================================================

output "ds_key" {
  description = "DeepSeek API密钥（敏感信息）"
  value       = var.ds_key
  sensitive   = true
}

output "ds_url" {
  description = "DeepSeek API URL"
  value       = var.ds_url
}

output "ali_api_key" {
  description = "阿里云API密钥（敏感信息）"
  value       = var.ali_api_key
  sensitive   = true
}

output "ali_url" {
  description = "阿里云API URL"
  value       = var.ali_url
}

output "ark_api_key" {
  description = "火山引擎API密钥（敏感信息）"
  value       = var.ark_api_key
  sensitive   = true
}

output "ark_url" {
  description = "火山引擎API URL"
  value       = var.ark_url
}

output "gpt_api_key" {
  description = "OpenAI API密钥（敏感信息）"
  value       = var.gpt_api_key
  sensitive   = true
}

output "embedding_model" {
  description = "嵌入模型名称"
  value       = var.embedding_model
}

output "normal_model" {
  description = "普通模型名称"
  value       = var.normal_model
}

output "image_model" {
  description = "图像模型名称"
  value       = var.image_model
}

output "mineru_api_key" {
  description = "MinerU API密钥（敏感信息）"
  value       = var.mineru_api_key
  sensitive   = true
}

output "mineru_url" {
  description = "MinerU API URL"
  value       = var.mineru_url
}

# ============================================================================
# 应用元数据输出
# ============================================================================

output "app_title" {
  description = "应用标题"
  value       = var.app_title
}

output "app_description" {
  description = "应用描述"
  value       = var.app_description
}

output "app_version" {
  description = "应用版本号"
  value       = var.app_version
}

output "environment" {
  description = "环境名称"
  value       = var.environment
}

output "debug" {
  description = "是否启用调试模式"
  value       = var.debug
}

output "log_level" {
  description = "日志级别"
  value       = var.log_level
}

# ============================================================================
# 文件处理配置输出
# ============================================================================

output "supported_extensions" {
  description = "支持的文件扩展名"
  value       = var.supported_extensions
}

output "max_file_size" {
  description = "最大文件大小（字节）"
  value       = var.max_file_size
}

output "max_image_size" {
  description = "最大图片大小（字节）"
  value       = var.max_image_size
}

# ============================================================================
# 模型参数配置输出
# ============================================================================

output "min_confidence_threshold" {
  description = "最小置信度阈值"
  value       = var.min_confidence_threshold
}

output "high_iou_threshold" {
  description = "高IOU阈值"
  value       = var.high_iou_threshold
}

output "default_embedding_dim" {
  description = "默认嵌入维度"
  value       = var.default_embedding_dim
}

output "default_top_k" {
  description = "默认Top K值"
  value       = var.default_top_k
}

output "default_batch_size" {
  description = "默认批次大小"
  value       = var.default_batch_size
}

output "default_epochs" {
  description = "默认训练轮数"
  value       = var.default_epochs
}

output "default_threshold" {
  description = "默认阈值"
  value       = var.default_threshold
}

# ============================================================================
# 订阅配置输出
# ============================================================================

output "free_plan_initial_credits" {
  description = "免费计划初始积分"
  value       = var.free_plan_initial_credits
}

# ============================================================================
# 用户数据目录配置输出
# ============================================================================

output "users_data_path" {
  description = "用户数据目录路径"
  value       = var.users_data_path
}

output "tmp_path" {
  description = "临时文件路径"
  value       = var.tmp_path
}

output "font_path" {
  description = "字体文件路径"
  value       = var.font_path
}

output "chromedriver_path" {
  description = "ChromeDriver路径"
  value       = var.chromedriver_path
}

output "algorithm" {
  description = "JWT算法"
  value       = var.algorithm
}

output "access_token_expire_minutes" {
  description = "访问令牌过期时间（分钟）"
  value       = var.access_token_expire_minutes
}

# ============================================================================
# ACK集群相关输出
# ============================================================================

# 注意：kubeconfig 和 cluster_id 输出已在 ack.tf 中定义
# 这里不再重复定义

# ============================================================================
# SLB相关输出
# ============================================================================

# 注意：slb_address, slb_id 已在 slb.tf 中定义
# 这里不再重复定义

