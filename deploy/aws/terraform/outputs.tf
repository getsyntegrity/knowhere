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
  description = "RDS端点"
  value       = aws_db_instance.postgres.endpoint
}

output "redis_endpoint" {
  description = "Redis端点"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "domain_name" {
  description = "域名"
  value       = var.domain_name
}

output "api_domain_name" {
  description = "API域名"
  value       = "api.${var.domain_name}"
}
