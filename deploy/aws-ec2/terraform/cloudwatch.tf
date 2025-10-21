# CloudWatch日志和告警配置

# CloudWatch日志组
resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/aws/ec2/${var.project_name}-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-logs"
  })
}

# CloudWatch日志组 - 应用特定日志
resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/aws/ec2/${var.project_name}-${var.environment}/api"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-api-logs"
  })
}

resource "aws_cloudwatch_log_group" "web_logs" {
  name              = "/aws/ec2/${var.project_name}-${var.environment}/web"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-web-logs"
  })
}

resource "aws_cloudwatch_log_group" "worker_logs" {
  name              = "/aws/ec2/${var.project_name}-${var.environment}/worker"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-worker-logs"
  })
}

# CloudWatch日志组 - Nginx日志
resource "aws_cloudwatch_log_group" "nginx_logs" {
  name              = "/aws/ec2/${var.project_name}-${var.environment}/nginx"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-nginx-logs"
  })
}

# SNS主题（用于告警通知）
resource "aws_sns_topic" "alerts" {
  count = var.notification_email != "" ? 1 : 0

  name = "${var.project_name}-${var.environment}-alerts"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-alerts"
  })
}

# SNS主题订阅
resource "aws_sns_topic_subscription" "email" {
  count = var.notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# CloudWatch告警 - CPU使用率
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project_name}-${var.environment}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors ec2 cpu utilization"
  alarm_actions       = var.notification_email != "" ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    InstanceId = local.instance_id
  }

  tags = var.common_tags
}

# CloudWatch告警 - 内存使用率
resource "aws_cloudwatch_metric_alarm" "memory_high" {
  alarm_name          = "${var.project_name}-${var.environment}-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "MemoryUtilization"
  namespace           = "CWAgent"
  period              = "300"
  statistic           = "Average"
  threshold           = "85"
  alarm_description   = "This metric monitors memory utilization"
  alarm_actions       = var.notification_email != "" ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    InstanceId = local.instance_id
  }

  tags = var.common_tags
}

# CloudWatch告警 - 磁盘使用率
resource "aws_cloudwatch_metric_alarm" "disk_high" {
  alarm_name          = "${var.project_name}-${var.environment}-disk-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DiskSpaceUtilization"
  namespace           = "CWAgent"
  period              = "300"
  statistic           = "Average"
  threshold           = "90"
  alarm_description   = "This metric monitors disk space utilization"
  alarm_actions       = var.notification_email != "" ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    InstanceId = local.instance_id
    Filesystem = "/"
  }

  tags = var.common_tags
}

# CloudWatch告警 - 实例状态检查
resource "aws_cloudwatch_metric_alarm" "instance_status_check" {
  alarm_name          = "${var.project_name}-${var.environment}-instance-status-check"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = "60"
  statistic           = "Maximum"
  threshold           = "0"
  alarm_description   = "This metric monitors ec2 instance status check"
  alarm_actions       = var.notification_email != "" ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    InstanceId = local.instance_id
  }

  tags = var.common_tags
}

# CloudWatch告警 - 系统状态检查
resource "aws_cloudwatch_metric_alarm" "system_status_check" {
  alarm_name          = "${var.project_name}-${var.environment}-system-status-check"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "StatusCheckFailed_System"
  namespace           = "AWS/EC2"
  period              = "60"
  statistic           = "Maximum"
  threshold           = "0"
  alarm_description   = "This metric monitors ec2 system status check"
  alarm_actions       = var.notification_email != "" ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    InstanceId = local.instance_id
  }

  tags = var.common_tags
}

# CloudWatch告警 - 应用健康检查（自定义指标）
resource "aws_cloudwatch_metric_alarm" "api_health_check" {
  alarm_name          = "${var.project_name}-${var.environment}-api-health-check"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HealthCheck"
  namespace           = "Knowhere/API"
  period              = "60"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "This metric monitors API health check"
  alarm_actions       = var.notification_email != "" ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    InstanceId = local.instance_id
  }

  tags = var.common_tags
}

# CloudWatch仪表板
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/EC2", "CPUUtilization", "InstanceId", local.instance_id],
            [".", "NetworkIn", ".", "."],
            [".", "NetworkOut", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "EC2 Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["CWAgent", "MemoryUtilization", "InstanceId", local.instance_id],
            [".", "DiskSpaceUtilization", ".", ".", "Filesystem", "/"]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "System Metrics"
          period  = 300
        }
      }
    ]
  })
}
