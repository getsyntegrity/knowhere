# 输出配置

output "instance_id" {
  description = "ECS实例ID"
  value       = local.instance_id
}

output "instance_public_ip" {
  description = "ECS实例公网IP"
  value       = local.instance_public_ip
}

output "instance_private_ip" {
  description = "ECS实例私网IP"
  value       = local.instance_private_ip
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
  value       = "ssh root@${local.instance_public_ip}"
}

output "vpc_id" {
  description = "VPC ID"
  value       = var.use_existing_vpc ? var.existing_vpc_id : alicloud_vpc.main[0].id
}

output "security_group_id" {
  description = "安全组ID"
  value       = local.app_security_group_id
}

output "database_endpoint" {
  description = "数据库连接端点"
  value       = var.use_existing_rds ? data.alicloud_db_instances.existing[0].instances[0].connection_string : alicloud_db_instance.main[0].connection_string
}

output "redis_endpoint" {
  description = "Redis连接端点"
  value       = var.use_existing_redis ? data.alicloud_kvstore_instances.existing[0].instances[0].connection_domain : alicloud_kvstore_instance.main[0].connection_domain
}

output "oss_bucket_name" {
  description = "OSS存储桶名称"
  value       = var.use_existing_oss ? var.existing_oss_bucket_name : alicloud_oss_bucket.main[0].bucket
}

output "oss_endpoint" {
  description = "OSS端点"
  value       = var.use_existing_oss ? "" : "${alicloud_oss_bucket.main[0].bucket}.oss-${var.region}.aliyuncs.com"
}

output "deployment_instructions" {
  description = "部署说明"
  value       = <<-EOT
    部署完成！请按以下步骤操作：

    1. SSH到实例：
       ssh root@${local.instance_public_ip}

    2. 配置DNS（在DNS服务提供商中）：
       ${var.api_subdomain}.${var.domain_name} -> ${local.instance_public_ip}
       ${var.web_subdomain}.${var.domain_name} -> ${local.instance_public_ip}

    3. 运行首次配置：
       cd /opt/knowhere/deploy/aliyun-ecs/scripts
       sudo ./provision-instance.sh

    4. 部署应用：
       sudo ./deploy-app.sh

    5. 访问应用：
       API: ${var.enable_ssl ? "https" : "http"}://${var.api_subdomain}.${var.domain_name}
       Web: ${var.enable_ssl ? "https" : "http"}://${var.web_subdomain}.${var.domain_name}
  EOT
}

