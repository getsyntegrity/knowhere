# S3存储桶 - 多环境支持
resource "aws_s3_bucket" "main" {
  bucket = "${var.project_name}-${var.environment}-storage-${random_string.bucket_suffix.result}"

  tags = {
    Name        = "${var.project_name}-${var.environment}-storage"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    id     = "cleanup_old_versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# S3事件通知配置 - 发送到SNS
resource "aws_s3_bucket_notification" "main" {
  bucket = aws_s3_bucket.main.id

  topic {
    topic_arn     = aws_sns_topic.s3_events.arn
    events        = ["s3:ObjectCreated:Put", "s3:ObjectCreated:Post", "s3:ObjectCreated:CompleteMultipartUpload"]
    filter_prefix = "uploads/"
  }
}

# 随机字符串用于存储桶名称唯一性
resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# 输出
output "s3_bucket_name" {
  description = "S3存储桶名称"
  value       = aws_s3_bucket.main.bucket
}

output "s3_bucket_arn" {
  description = "S3存储桶ARN"
  value       = aws_s3_bucket.main.arn
}
