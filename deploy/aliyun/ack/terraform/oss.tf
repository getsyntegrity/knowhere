# OSS对象存储 - 多环境支持
resource "alicloud_oss_bucket" "main" {
  bucket = "${var.project_name}-${var.environment}-storage-${random_string.bucket_suffix.result}"
  acl    = "private"

  # 版本控制
  versioning {
    status = "Enabled"
  }

  # 服务器端加密
  server_side_encryption_rule {
    sse_algorithm = "AES256"
  }

  # 生命周期规则
  lifecycle_rule {
    id      = "cleanup-old-versions"
    enabled = true

    expiration {
      days = var.environment == "prod" ? 90 : 30
    }

    noncurrent_version_expiration {
      noncurrent_days = var.environment == "prod" ? 30 : 7
    }
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-storage"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 随机字符串用于存储桶名称唯一性
resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# 输出
output "oss_bucket_name" {
  description = "OSS存储桶名称"
  value       = alicloud_oss_bucket.main.bucket
}

output "oss_bucket_endpoint" {
  description = "OSS存储桶Endpoint"
  value       = "https://${alicloud_oss_bucket.main.bucket}.oss-${var.region}.aliyuncs.com"
}

