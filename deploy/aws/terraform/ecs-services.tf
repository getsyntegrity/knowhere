# ECS服务定义 - 多环境支持

# 后端服务
resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-${var.environment}-backend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 2
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
  desired_count   = 2
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
  desired_count   = 2
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
      image = "${aws_ecr_repository.backend.repository_url}:main-latest"
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
          value = tostring(var.debug)
        },
        {
          name  = "LOG_LEVEL"
          value = var.log_level
        },
        {
          name  = "PYTHONUNBUFFERED"
          value = "1"
        },
        {
          name  = "APP_TITLE"
          value = var.app_title
        },
        {
          name  = "APP_VERSION"
          value = var.app_version
        },
        {
          name  = "APP_DESCRIPTION"
          value = var.app_description
        },
        {
          name  = "TMP_PATH"
          value = var.tmp_path
        },
        {
          name  = "FONT_PATH"
          value = var.font_path
        },
        {
          name  = "CHROMEDRIVER_PATH"
          value = var.chromedriver_path
        },
        {
          name  = "ALGORITHM"
          value = var.algorithm
        },
        {
          name  = "ACCESS_TOKEN_EXPIRE_MINUTES"
          value = tostring(var.access_token_expire_minutes)
        },
        {
          name  = "DB_SSL_MODE"
          value = var.db_ssl_mode
        },
        {
          name  = "REDIS_DATABASE"
          value = tostring(var.redis_database)
        },
        {
          name  = "RABBITMQ_PORT"
          value = "5671"
        },
        {
          name  = "RABBITMQ_VHOST"
          value = "/"
        },
        {
          name  = "MESSAGE_BROKER_TYPE"
          value = var.message_broker_type
        },
        {
          name  = "CELERY_RESULT_BACKEND"
          value = var.celery_result_backend
        },
        {
          name  = "S3_TYPE"
          value = var.s3_type
        },
        {
          name  = "S3_BUCKET_NAME"
          value = aws_s3_bucket.main.bucket
        },
        {
          name  = "S3_ENDPOINT_URL"
          value = var.s3_endpoint_url != "" ? var.s3_endpoint_url : "https://s3.${var.aws_region}.amazonaws.com"
        },
        {
          name  = "S3_PRIVATE_DOMAIN"
          value = var.s3_private_domain != "" ? var.s3_private_domain : "https://${aws_s3_bucket.main.bucket}.s3.${var.aws_region}.amazonaws.com"
        },
        {
          name  = "S3_TEMP_PATH"
          value = var.s3_temp_path
        },
        {
          name  = "S3_REGION"
          value = var.s3_region
        },
        {
          name  = "S3_USE_SSL"
          value = tostring(var.s3_use_ssl)
        },
        {
          name  = "S3_ADDRESSING_STYLE"
          value = var.s3_addressing_style
        },
        {
          name  = "SNS_TOPIC_ARN"
          value = aws_sns_topic.s3_events.arn
        },
        {
          name  = "SNS_SIGNATURE_VERIFICATION"
          value = tostring(var.sns_signature_verification)
        },
        {
          name  = "SUPPORTED_EXTENSIONS"
          value = var.supported_extensions
        },
        {
          name  = "MAX_FILE_SIZE"
          value = tostring(var.max_file_size)
        },
        {
          name  = "MAX_IMAGE_SIZE"
          value = tostring(var.max_image_size)
        },
        {
          name  = "MIN_CONFIDENCE_THRESHOLD"
          value = tostring(var.min_confidence_threshold)
        },
        {
          name  = "HIGH_IOU_THRESHOLD"
          value = tostring(var.high_iou_threshold)
        },
        {
          name  = "DEFAULT_EMBEDDING_DIM"
          value = tostring(var.default_embedding_dim)
        },
        {
          name  = "DEFAULT_TOP_K"
          value = tostring(var.default_top_k)
        },
        {
          name  = "DEFAULT_BATCH_SIZE"
          value = tostring(var.default_batch_size)
        },
        {
          name  = "DEFAULT_EPOCHS"
          value = tostring(var.default_epochs)
        },
        {
          name  = "DEFAULT_THRESHOLD"
          value = tostring(var.default_threshold)
        },
        {
          name  = "FREE_PLAN_INITIAL_CREDITS"
          value = tostring(var.free_plan_initial_credits)
        },
        {
          name  = "USERS_DATA_PATH"
          value = var.users_data_path
        },
        {
          name  = "SMTP_HOST"
          value = var.smtp_host
        },
        {
          name  = "SMTP_PORT"
          value = tostring(var.smtp_port)
        },
        {
          name  = "SMTP_USER"
          value = var.smtp_user
        },
        {
          name  = "EMAILS_FROM_EMAIL"
          value = var.emails_from_email
        },
        {
          name  = "EMAILS_FROM_NAME"
          value = var.emails_from_name
        },
        {
          name  = "DS_URL"
          value = var.ds_url
        },
        {
          name  = "ALI_URL"
          value = var.ali_url
        },
        {
          name  = "ARK_URL"
          value = var.ark_url
        },
        {
          name  = "EMBEDDING_MODEL"
          value = var.embedding_model
        },
        {
          name  = "NORMOL_MODEL"
          value = var.normal_model
        },
        {
          name  = "IMAGE_MODEL"
          value = var.image_model
        },
        {
          name  = "MINERU_URL"
          value = var.mineru_url
        }
      ]
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "REDIS_HOST"
          valueFrom = aws_secretsmanager_secret.redis_host.arn
        },
        {
          name      = "REDIS_PORT"
          valueFrom = aws_secretsmanager_secret.redis_port.arn
        },
        {
          name      = "REDIS_PASSWORD"
          valueFrom = aws_secretsmanager_secret.redis_password.arn
        },
        {
          name      = "RABBITMQ_HOST"
          valueFrom = aws_secretsmanager_secret.rabbitmq_host.arn
        },
        {
          name      = "RABBITMQ_USER"
          valueFrom = aws_secretsmanager_secret.rabbitmq_username.arn
        },
        {
          name      = "RABBITMQ_PASSWORD"
          valueFrom = aws_secretsmanager_secret.rabbitmq_password.arn
        },
        {
          name      = "S3_ACCESS_KEY_ID"
          valueFrom = aws_secretsmanager_secret.s3_access_key.arn
        },
        {
          name      = "S3_SECRET_ACCESS_KEY"
          valueFrom = aws_secretsmanager_secret.s3_secret_key.arn
        },
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.secret_key.arn
        },
        {
          name      = "USERS_VERIFY_TOKEN_SECRET"
          valueFrom = aws_secretsmanager_secret.users_verify_token_secret.arn
        },
        {
          name      = "USERS_RESET_PASSWORD_TOKEN_SECRET"
          valueFrom = aws_secretsmanager_secret.users_reset_password_token_secret.arn
        },
        {
          name      = "WEBHOOK_SIGNING_SECRET"
          valueFrom = aws_secretsmanager_secret.webhook_signing_secret.arn
        },
        {
          name      = "S3_WEBHOOK_AUTH_TOKEN"
          valueFrom = aws_secretsmanager_secret.s3_webhook_auth_token.arn
        },
        {
          name      = "CELERY_BROKER_URL"
          valueFrom = aws_secretsmanager_secret.celery_broker_url.arn
        },
        {
          name      = "STRIPE_SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.stripe_secret_key.arn
        },
        {
          name      = "STRIPE_WEBHOOK_SECRET"
          valueFrom = aws_secretsmanager_secret.stripe_webhook_secret.arn
        },
        {
          name      = "RESEND_API_KEY"
          valueFrom = aws_secretsmanager_secret.resend_api_key.arn
        },
        {
          name      = "MOESIF_APPLICATION_ID"
          valueFrom = aws_secretsmanager_secret.moesif_application_id.arn
        },
        {
          name      = "GOOGLE_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.google_client_id.arn
        },
        {
          name      = "GOOGLE_CLIENT_SECRET"
          valueFrom = aws_secretsmanager_secret.google_client_secret.arn
        },
        {
          name      = "GITHUB_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.github_client_id.arn
        },
        {
          name      = "GITHUB_CLIENT_SECRET"
          valueFrom = aws_secretsmanager_secret.github_client_secret.arn
        },
        {
          name      = "APPLE_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.apple_client_id.arn
        },
        {
          name      = "APPLE_CLIENT_SECRET"
          valueFrom = aws_secretsmanager_secret.apple_client_secret.arn
        },
        {
          name      = "SMTP_PASSWORD"
          valueFrom = aws_secretsmanager_secret.smtp_password.arn
        },
        {
          name      = "DS_KEY"
          valueFrom = aws_secretsmanager_secret.ds_key.arn
        },
        {
          name      = "ALI_API_KEY"
          valueFrom = aws_secretsmanager_secret.ali_api_key.arn
        },
        {
          name      = "ARK_API_KEY"
          valueFrom = aws_secretsmanager_secret.ark_api_key.arn
        },
        {
          name      = "GPT_API_KEY"
          valueFrom = aws_secretsmanager_secret.gpt_api_key.arn
        },
        {
          name      = "MINERU_API_KEY"
          valueFrom = aws_secretsmanager_secret.mineru_api_key.arn
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
      image = "${aws_ecr_repository.frontend.repository_url}:main-latest"
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
          value     = "https://api.${var.domain_name}"
        },
        {
          name      = "NEXT_PUBLIC_POSTHOG_KEY"
          valueFrom = aws_secretsmanager_secret.posthog_key.arn
        },
        {
          name      = "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY"
          valueFrom = aws_secretsmanager_secret.stripe_publishable_key.arn
        },
        {
          name      = "GOOGLE_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.google_client_id.arn
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
      image     = "${aws_ecr_repository.worker.repository_url}:main-latest"
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
          value = tostring(var.debug)
        },
        {
          name  = "LOG_LEVEL"
          value = var.log_level
        },
        {
          name  = "PYTHONUNBUFFERED"
          value = "1"
        },
        {
          name  = "APP_VERSION"
          value = var.app_version
        },
        {
          name  = "S3_TYPE"
          value = var.s3_type
        },
        {
          name  = "S3_BUCKET_NAME"
          value = aws_s3_bucket.main.bucket
        },
        {
          name  = "S3_ENDPOINT_URL"
          value = var.s3_endpoint_url != "" ? var.s3_endpoint_url : "https://s3.${var.aws_region}.amazonaws.com"
        },
        {
          name  = "S3_PRIVATE_DOMAIN"
          value = var.s3_private_domain != "" ? var.s3_private_domain : "https://${aws_s3_bucket.main.bucket}.s3.${var.aws_region}.amazonaws.com"
        },
        {
          name  = "S3_TEMP_PATH"
          value = var.s3_temp_path
        },
        {
          name  = "S3_REGION"
          value = var.s3_region
        },
        {
          name  = "S3_USE_SSL"
          value = tostring(var.s3_use_ssl)
        },
        {
          name  = "S3_ADDRESSING_STYLE"
          value = var.s3_addressing_style
        },
        {
          name  = "SNS_TOPIC_ARN"
          value = aws_sns_topic.s3_events.arn
        },
        {
          name  = "SNS_SIGNATURE_VERIFICATION"
          value = tostring(var.sns_signature_verification)
        },
        {
          name  = "RABBITMQ_PORT"
          value = "5671"
        },
        {
          name  = "RABBITMQ_VHOST"
          value = "/"
        },
        {
          name  = "MESSAGE_BROKER_TYPE"
          value = var.message_broker_type
        },
        {
          name  = "CELERY_RESULT_BACKEND"
          value = var.celery_result_backend
        },
        {
          name  = "USERS_DATA_PATH"
          value = var.users_data_path
        },
        {
          name  = "DS_URL"
          value = var.ds_url
        },
        {
          name  = "ALI_URL"
          value = var.ali_url
        },
        {
          name  = "ARK_URL"
          value = var.ark_url
        },
        {
          name  = "EMBEDDING_MODEL"
          value = var.embedding_model
        },
        {
          name  = "NORMOL_MODEL"
          value = var.normal_model
        },
        {
          name  = "IMAGE_MODEL"
          value = var.image_model
        },
        {
          name  = "MINERU_URL"
          value = var.mineru_url
        }
      ]
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "REDIS_HOST"
          valueFrom = aws_secretsmanager_secret.redis_host.arn
        },
        {
          name      = "REDIS_PORT"
          valueFrom = aws_secretsmanager_secret.redis_port.arn
        },
        {
          name      = "REDIS_PASSWORD"
          valueFrom = aws_secretsmanager_secret.redis_password.arn
        },
        {
          name      = "RABBITMQ_HOST"
          valueFrom = aws_secretsmanager_secret.rabbitmq_host.arn
        },
        {
          name      = "RABBITMQ_USER"
          valueFrom = aws_secretsmanager_secret.rabbitmq_username.arn
        },
        {
          name      = "RABBITMQ_PASSWORD"
          valueFrom = aws_secretsmanager_secret.rabbitmq_password.arn
        },
        {
          name      = "S3_ACCESS_KEY_ID"
          valueFrom = aws_secretsmanager_secret.s3_access_key.arn
        },
        {
          name      = "S3_SECRET_ACCESS_KEY"
          valueFrom = aws_secretsmanager_secret.s3_secret_key.arn
        },
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.secret_key.arn
        },
        {
          name      = "CELERY_BROKER_URL"
          valueFrom = aws_secretsmanager_secret.celery_broker_url.arn
        },
        {
          name      = "DS_KEY"
          valueFrom = aws_secretsmanager_secret.ds_key.arn
        },
        {
          name      = "ALI_API_KEY"
          valueFrom = aws_secretsmanager_secret.ali_api_key.arn
        },
        {
          name      = "ARK_API_KEY"
          valueFrom = aws_secretsmanager_secret.ark_api_key.arn
        },
        {
          name      = "GPT_API_KEY"
          valueFrom = aws_secretsmanager_secret.gpt_api_key.arn
        },
        {
          name      = "MINERU_API_KEY"
          valueFrom = aws_secretsmanager_secret.mineru_api_key.arn
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
