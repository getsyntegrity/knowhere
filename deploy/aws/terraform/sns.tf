# SNS Topic - 用于S3事件通知
resource "aws_sns_topic" "s3_events" {
  name = "${var.project_name}-${var.environment}-s3-events"

  tags = {
    Name        = "${var.project_name}-${var.environment}-s3-events"
    Environment = var.environment
    Project     = var.project_name
  }
}

# SNS Topic策略 - 允许S3发布事件
resource "aws_sns_topic_policy" "s3_events" {
  arn = aws_sns_topic.s3_events.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.s3_events.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# SNS订阅 - 订阅到API webhook endpoint
resource "aws_sns_topic_subscription" "s3_events_webhook" {
  topic_arn = aws_sns_topic.s3_events.arn
  protocol  = "https"
  endpoint  = var.api_webhook_endpoint

  # 重试策略
  delivery_policy = jsonencode({
    healthyRetryPolicy = {
      minDelayTarget     = 1
      maxDelayTarget     = 60
      numRetries         = 3
      numMaxDelayRetries = 2
      numNoDelayRetries  = 0
      numMinDelayRetries = 1
    }
  })
}

# 输出
output "sns_topic_arn" {
  description = "SNS Topic ARN"
  value       = aws_sns_topic.s3_events.arn
}

