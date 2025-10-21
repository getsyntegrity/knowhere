# 输出信息

output "instance_id" {
  description = "EC2实例ID"
  value       = local.instance_id
}

output "instance_public_ip" {
  description = "EC2实例公网IP"
  value       = local.instance_public_ip
}

output "instance_private_ip" {
  description = "EC2实例私网IP"
  value       = local.instance_private_ip
}

output "instance_dns_name" {
  description = "EC2实例公网DNS"
  value       = local.instance_public_dns
}

output "api_url" {
  description = "API访问URL"
  value       = var.enable_ssl ? "https://${var.api_subdomain}.${var.domain_name}" : "http://${var.api_subdomain}.${var.domain_name}"
}

output "web_url" {
  description = "Web访问URL"
  value       = var.enable_ssl ? "https://${var.web_subdomain}.${var.domain_name}" : "http://${var.web_subdomain}.${var.domain_name}"
}

output "ssh_command" {
  description = "SSH连接命令"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ubuntu@${local.instance_public_ip}"
}

output "vpc_id" {
  description = "VPC ID"
  value       = var.use_existing_vpc ? var.existing_vpc_id : aws_vpc.main[0].id
}

output "security_group_id" {
  description = "安全组ID"
  value       = var.use_existing_security_group ? var.existing_security_group_id : aws_security_group.app_server[0].id
}

output "database_endpoint" {
  description = "数据库连接端点"
  value       = var.use_existing_rds ? data.aws_db_instance.existing[0].endpoint : aws_db_instance.main[0].endpoint
}

output "redis_endpoint" {
  description = "Redis连接端点"
  value       = var.use_existing_redis ? data.aws_elasticache_replication_group.existing[0].primary_endpoint_address : aws_elasticache_replication_group.main[0].primary_endpoint_address
}

output "s3_bucket_name" {
  description = "S3存储桶名称"
  value       = var.use_existing_s3 ? var.existing_s3_bucket_name : aws_s3_bucket.main[0].id
}

output "cloudwatch_log_group" {
  description = "CloudWatch日志组"
  value       = aws_cloudwatch_log_group.app_logs.name
}

output "deployment_instructions" {
  description = "部署说明"
  value       = <<-EOT
    部署完成！请按以下步骤操作：

    1. SSH到实例：
       ssh -i ~/.ssh/${var.key_pair_name}.pem ubuntu@${local.instance_public_ip}

    2. 配置DNS（在Squarespace中）：
       ${var.api_subdomain}.${var.domain_name} -> ${local.instance_public_ip}
       ${var.web_subdomain}.${var.domain_name} -> ${local.instance_public_ip}

    3. 运行首次配置：
       cd /opt/knowhere/deploy/aws-ec2/scripts
       sudo ./provision-instance.sh

    4. 部署应用：
       sudo ./deploy-app.sh

    5. 访问应用：
       API: ${var.enable_ssl ? "https" : "http"}://${var.api_subdomain}.${var.domain_name}
       Web: ${var.enable_ssl ? "https" : "http"}://${var.web_subdomain}.${var.domain_name}
  EOT
}
