# DNS配置 - 多环境域名
data "alicloud_dns_domains" "main" {
  domain_name = var.domain_name
}

# DNS记录 - API域名
resource "alicloud_dns_record" "api" {
  name        = var.environment == "prod" ? "api" : "${var.environment}-api"
  host_record = var.environment == "prod" ? "api" : "${var.environment}-api"
  type        = "A"
  value       = alicloud_slb_load_balancer.main.address  # 使用SLB IP
  ttl         = 600
  domain_name = var.domain_name
}

# DNS记录 - Web域名
resource "alicloud_dns_record" "web" {
  name        = var.environment == "prod" ? "@" : var.environment
  host_record = var.environment == "prod" ? "@" : var.environment
  type        = "A"
  value       = alicloud_slb_load_balancer.main.address
  ttl         = 600
  domain_name = var.domain_name
}

