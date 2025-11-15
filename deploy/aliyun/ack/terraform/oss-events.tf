# OSS事件通知配置 - 多环境支持
# 注意：阿里云OSS事件通知需要通过API配置，Terraform provider可能不支持
# 这里提供配置说明，实际配置需要通过脚本或控制台完成

# OSS事件通知配置脚本
# 需要在部署后运行脚本来配置事件通知

# 输出配置信息
output "oss_event_config" {
  description = "OSS事件通知配置信息"
  value = {
    bucket_name = alicloud_oss_bucket.main.bucket
    events = [
      "oss:ObjectCreated:PutObject",
      "oss:ObjectCreated:PostObject",
      "oss:ObjectCreated:CompleteMultipartUpload"
    ]
    filter_prefix = "uploads/"
    callback_url  = var.api_webhook_endpoint != "" ? var.api_webhook_endpoint : "https://${var.environment == "prod" ? "api" : (var.environment == "dev" ? "apidev" : (var.environment == "test" ? "apitest" : "${var.environment}-api"))}.${var.domain_name}/v1/internal/oss-events"
  }
}

