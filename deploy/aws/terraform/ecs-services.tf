# ECS服务定义 - 多环境支持

# 后端服务
resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-${var.environment}-backend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "knowhere-backend"
    container_port   = 5005
  }

  depends_on = [aws_lb_listener.https]

  tags = {
    Name        = "${var.project_name}-${var.environment}-backend-service"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 前端服务
resource "aws_ecs_service" "frontend" {
  name            = "${var.project_name}-${var.environment}-frontend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "knowhere-frontend"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.https]

  tags = {
    Name        = "${var.project_name}-${var.environment}-frontend-service"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Worker服务
resource "aws_ecs_service" "worker" {
  name            = "${var.project_name}-${var.environment}-worker-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-worker-service"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ECS任务定义 - 多环境支持
resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-${var.environment}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "knowhere-backend"
      image = "${aws_ecr_repository.backend.repository_url}:${var.environment}-latest"
      portMappings = [
        {
          containerPort = 5005
          protocol      = "tcp"
        }
      ]
      essential = true
      environment = [
        {
          name  = "ENVIRONMENT"
          value = "production"
        },
        {
          name  = "DEBUG"
          value = "false"
        },
        {
          name  = "LOG_LEVEL"
          value = "INFO"
        }
      ]
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/database-url"
        },
        {
          name      = "REDIS_HOST"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/redis-host"
        },
        {
          name      = "REDIS_PASSWORD"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/redis-password"
        },
        {
          name      = "RABBITMQ_HOST"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/rabbitmq-host"
        },
        {
          name      = "RABBITMQ_PASSWORD"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/rabbitmq-password"
        },
        {
          name      = "S3_BUCKET_NAME"
          value     = aws_s3_bucket.main.bucket
        },
        {
          name      = "S3_ACCESS_KEY_ID"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/s3-access-key"
        },
        {
          name      = "S3_SECRET_ACCESS_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/s3-secret-key"
        },
        {
          name      = "SNS_TOPIC_ARN"
          value     = aws_sns_topic.s3_events.arn
        },
        {
          name      = "SECRET_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/secret-key"
        },
        {
          name      = "STRIPE_SECRET_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/stripe-secret-key"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:5005/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name        = "${var.project_name}-${var.environment}-backend"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.project_name}-${var.environment}-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "knowhere-frontend"
      image = "${aws_ecr_repository.frontend.repository_url}:${var.environment}-latest"
      portMappings = [
        {
          containerPort = 3000
          protocol      = "tcp"
        }
      ]
      essential = true
      environment = [
        {
          name  = "NODE_ENV"
          value = "production"
        },
        {
          name  = "NEXT_TELEMETRY_DISABLED"
          value = "1"
        },
        {
          name  = "NEXT_PUBLIC_POSTHOG_HOST"
          value = "https://app.posthog.com"
        }
      ]
      secrets = [
        {
          name      = "NEXT_PUBLIC_API_URL"
          value     = var.environment == "prod" ? "https://api.${var.domain_name}" : "https://${var.environment}-api.${var.domain_name}"
        },
        {
          name      = "NEXT_PUBLIC_POSTHOG_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/posthog-key"
        },
        {
          name      = "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/stripe-publishable-key"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:3000 || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])

  tags = {
    Name        = "${var.project_name}-${var.environment}-frontend"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project_name}-${var.environment}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  # EFS挂载配置 - 模型缓存
  volume {
    name = "model-cache"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.model_cache.id
      root_directory     = "/"
      transit_encryption = "ENABLED"

      authorization_config {
        iam = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "knowhere-worker"
      image     = "${aws_ecr_repository.worker.repository_url}:${var.environment}-latest"
      essential = true
      
      # EFS挂载点
      mountPoints = [
        {
          sourceVolume  = "model-cache"
          containerPath = "/mnt/models/huggingface"
          readOnly      = false
        }
      ]
      
      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "HF_HOME"
          value = "/mnt/models/huggingface"
        },
        {
          name  = "TRANSFORMERS_CACHE"
          value = "/mnt/models/huggingface"
        },
        {
          name  = "DEBUG"
          value = "false"
        },
        {
          name  = "LOG_LEVEL"
          value = "INFO"
        }
      ]
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/database-url"
        },
        {
          name      = "REDIS_HOST"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/redis-host"
        },
        {
          name      = "REDIS_PASSWORD"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/redis-password"
        },
        {
          name      = "RABBITMQ_HOST"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/rabbitmq-host"
        },
        {
          name      = "RABBITMQ_PASSWORD"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/rabbitmq-password"
        },
        {
          name      = "S3_BUCKET_NAME"
          value     = aws_s3_bucket.main.bucket
        },
        {
          name      = "S3_ACCESS_KEY_ID"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/s3-access-key"
        },
        {
          name      = "S3_SECRET_ACCESS_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/s3-secret-key"
        },
        {
          name      = "SNS_TOPIC_ARN"
          value     = aws_sns_topic.s3_events.arn
        },
        {
          name      = "SECRET_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:knowhere/${var.environment}/secret-key"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"from app.core.celery_app import celery_app; celery_app.control.inspect().stats()\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name        = "${var.project_name}-${var.environment}-worker"
    Environment = var.environment
    Project     = var.project_name
  }
}
