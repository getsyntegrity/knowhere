# DNS配置 - 多环境域名
# 注意：DNS 记录需要通过阿里云控制台或 API 手动配置
# Terraform Provider 对 DNS 记录的支持可能有限
# 以下配置仅供参考，实际部署时可能需要通过其他方式配置 DNS

# DNS记录 - API域名（如果 Provider 支持）
# resource "alicloud_dns_record" "api" {
#   host_record = var.environment == "prod" ? "api" : (var.environment == "dev" ? "apidev" : (var.environment == "test" ? "apitest" : "${var.environment}-api"))
#   type        = "A"
#   value       = alicloud_slb_load_balancer.main.address
#   ttl         = 600
#   domain_name = var.domain_name
# }

# DNS记录 - Web域名（如果 Provider 支持）
# resource "alicloud_dns_record" "web" {
#   host_record = var.environment == "prod" ? "@" : var.environment
#   type        = "A"
#   value       = alicloud_slb_load_balancer.main.address
#   ttl         = 600
#   domain_name = var.domain_name
# }

# 输出 SLB 地址，用于手动配置 DNS
output "slb_address_for_dns" {
  description = "SLB IP地址，用于手动配置DNS记录"
  value       = alicloud_slb_load_balancer.main.address
}

