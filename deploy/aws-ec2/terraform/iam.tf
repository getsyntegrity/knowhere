# IAM角色和策略配置

# EC2实例角色
resource "aws_iam_role" "app_server" {
  name = "${var.project_name}-${var.environment}-app-server-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

# EC2实例配置文件
resource "aws_iam_instance_profile" "app_server" {
  name = "${var.project_name}-${var.environment}-app-server-profile"
  role = aws_iam_role.app_server.name

  tags = var.common_tags
}

# CloudWatch Agent策略
resource "aws_iam_policy" "cloudwatch_agent" {
  name = "${var.project_name}-${var.environment}-cloudwatch-agent-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "ec2:DescribeVolumes",
          "ec2:DescribeTags",
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.common_tags
}

# S3访问策略
resource "aws_iam_policy" "s3_access" {
  name = "${var.project_name}-${var.environment}-s3-access-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.use_existing_s3 ? data.aws_s3_bucket.existing[0].arn : aws_s3_bucket.main[0].arn,
          "${var.use_existing_s3 ? data.aws_s3_bucket.existing[0].arn : aws_s3_bucket.main[0].arn}/*"
        ]
      }
    ]
  })

  tags = var.common_tags
}

# Secrets Manager访问策略
resource "aws_iam_policy" "secrets_manager" {
  name = "${var.project_name}-${var.environment}-secrets-manager-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*"
        ]
      }
    ]
  })

  tags = var.common_tags
}

# RDS访问策略
resource "aws_iam_policy" "rds_access" {
  name = "${var.project_name}-${var.environment}-rds-access-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:DescribeDBClusters"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.common_tags
}

# ElastiCache访问策略
resource "aws_iam_policy" "elasticache_access" {
  name = "${var.project_name}-${var.environment}-elasticache-access-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "elasticache:DescribeReplicationGroups",
          "elasticache:DescribeCacheClusters"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.common_tags
}

# SSM访问策略（用于调试）
resource "aws_iam_policy" "ssm_access" {
  name = "${var.project_name}-${var.environment}-ssm-access-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:UpdateInstanceInformation",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.common_tags
}

# 将策略附加到角色
resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.app_server.name
  policy_arn = aws_iam_policy.cloudwatch_agent.arn
}

resource "aws_iam_role_policy_attachment" "s3_access" {
  role       = aws_iam_role.app_server.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "aws_iam_role_policy_attachment" "secrets_manager" {
  role       = aws_iam_role.app_server.name
  policy_arn = aws_iam_policy.secrets_manager.arn
}

resource "aws_iam_role_policy_attachment" "rds_access" {
  role       = aws_iam_role.app_server.name
  policy_arn = aws_iam_policy.rds_access.arn
}

resource "aws_iam_role_policy_attachment" "elasticache_access" {
  role       = aws_iam_role.app_server.name
  policy_arn = aws_iam_policy.elasticache_access.arn
}

resource "aws_iam_role_policy_attachment" "ssm_access" {
  role       = aws_iam_role.app_server.name
  policy_arn = aws_iam_policy.ssm_access.arn
}

# 附加AWS托管策略
resource "aws_iam_role_policy_attachment" "ssm_managed_instance_core" {
  role       = aws_iam_role.app_server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
