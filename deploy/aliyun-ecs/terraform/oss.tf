# OSS对象存储配置

# OSS存储桶（如果不使用现有OSS）
resource "alicloud_oss_bucket" "main" {
  count  = var.use_existing_oss ? 0 : 1
  bucket = "${var.project_name}-${var.environment}-storage-${random_string.bucket_suffix[0].result}"
  acl    = "private"
  
  # 加密配置
  server_side_encryption_rule {
    sse_algorithm = "AES256"
  }
  
  # 版本控制
  versioning {
    status = "Enabled"
  }
  
  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-storage"
  })
}

# 随机字符串用于OSS存储桶名称唯一性
resource "random_string" "bucket_suffix" {
  count = var.use_existing_oss ? 0 : 1

  length  = 8
  special = false
  upper   = false
}

