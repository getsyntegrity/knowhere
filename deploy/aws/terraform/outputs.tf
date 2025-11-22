# 输出值
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "公共子网ID列表"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "私有子网ID列表"
  value       = aws_subnet.private[*].id
}

output "ecs_cluster_id" {
  description = "ECS集群ID"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_arn" {
  description = "ECS集群ARN"
  value       = aws_ecs_cluster.main.arn
}

output "alb_dns_name" {
  description = "负载均衡器DNS名称"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "负载均衡器Zone ID"
  value       = aws_lb.main.zone_id
}

output "backend_target_group_arn" {
  description = "后端目标组ARN"
  value       = aws_lb_target_group.backend.arn
}

output "frontend_target_group_arn" {
  description = "前端目标组ARN"
  value       = aws_lb_target_group.frontend.arn
}

output "ecr_backend_repository_url" {
  description = "后端ECR仓库URL"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_repository_url" {
  description = "前端ECR仓库URL"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecr_worker_repository_url" {
  description = "Worker ECR仓库URL"
  value       = aws_ecr_repository.worker.repository_url
}

output "rds_endpoint" {
  description = "RDS Serverless v2集群端点"
  value       = aws_rds_cluster.postgres.endpoint
}

output "rds_reader_endpoint" {
  description = "RDS Serverless v2集群只读端点"
  value       = aws_rds_cluster.postgres.reader_endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Serverless Redis端点"
  value       = aws_elasticache_serverless_cache.redis.endpoint[0].address
}

output "redis_port" {
  description = "ElastiCache Serverless Redis端口"
  value       = aws_elasticache_serverless_cache.redis.endpoint[0].port
}

output "domain_name" {
  description = "域名"
  value       = var.domain_name
}

output "api_domain_name" {
  description = "API域名"
  value       = "api.${var.domain_name}"
}

output "redis_host_secret_arn" {
  description = "Redis host Secret ARN"
  value       = aws_secretsmanager_secret.redis_host.arn
}

output "redis_port_secret_arn" {
  description = "Redis port Secret ARN"
  value       = aws_secretsmanager_secret.redis_port.arn
}

output "redis_password_secret_arn" {
  description = "Redis password Secret ARN"
  value       = aws_secretsmanager_secret.redis_password.arn
}

# Note: mq_broker_host_secret_arn and mq_broker_password_secret_arn are defined in mq.tf
# Removed duplicate definitions here to avoid conflicts

output "database_url_secret_arn" {
  description = "Database URL Secret ARN"
  value       = aws_secretsmanager_secret.database_url.arn
}

output "s3_access_key_secret_arn" {
  description = "S3 Access Key Secret ARN"
  value       = aws_secretsmanager_secret.s3_access_key.arn
}

output "s3_secret_key_secret_arn" {
  description = "S3 Secret Key Secret ARN"
  value       = aws_secretsmanager_secret.s3_secret_key.arn
}

output "secret_key_secret_arn" {
  description = "Application Secret Key Secret ARN"
  value       = aws_secretsmanager_secret.secret_key.arn
}

output "stripe_secret_key_secret_arn" {
  description = "Stripe Secret Key Secret ARN"
  value       = aws_secretsmanager_secret.stripe_secret_key.arn
}

output "stripe_publishable_key_secret_arn" {
  description = "Stripe Publishable Key Secret ARN"
  value       = aws_secretsmanager_secret.stripe_publishable_key.arn
}

output "posthog_key_secret_arn" {
  description = "PostHog Key Secret ARN"
  value       = aws_secretsmanager_secret.posthog_key.arn
}

# DNS配置输出（用于外部DNS提供商手动配置）
output "manual_dns_records" {
  description = "需要在外部DNS提供商手动配置的DNS记录"
  value = {
    # ALB DNS记录（A记录，使用ALIAS/CNAME指向ALB）
    alb_dns_name = aws_lb.main.dns_name
    alb_zone_id  = aws_lb.main.zone_id
    
    # 需要创建的A记录（指向ALB）
    a_records = {
      api = "api.${var.domain_name}"
      web = var.domain_name
    }
    
    # ACM证书验证记录（CNAME类型）
    certificate_validation_records = var.use_route53 ? {} : {
      for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
        name   = dvo.resource_record_name
        type   = dvo.resource_record_type
        value  = dvo.resource_record_value
        domain = dvo.domain_name
      }
    }
  }
}

output "certificate_arn" {
  description = "ACM证书ARN（用于检查验证状态）"
  value       = aws_acm_certificate.main.arn
}

output "certificate_validation_status" {
  description = "证书验证状态说明"
  value = var.use_route53 ? "使用Route53自动验证" : "需要在外部DNS提供商手动创建验证记录，见 manual_dns_records 输出"
}
