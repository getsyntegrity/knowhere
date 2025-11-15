# SLB负载均衡配置 - 多环境支持
resource "alicloud_slb_load_balancer" "main" {
  load_balancer_name = "${var.project_name}-${var.environment}-slb"
  address_type       = "internet"
  load_balancer_spec  = var.environment == "prod" ? "slb.s2.large" : "slb.s1.small"
  vswitch_id         = alicloud_vswitch.public[0].id
  master_zone_id     = data.alicloud_zones.available.zones[0].id
  slave_zone_id      = data.alicloud_zones.available.zones[1].id

  tags = {
    Name        = "${var.project_name}-${var.environment}-slb"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 后端服务器组 - API
# 注意：后端服务器需要在 Kubernetes 集群和节点创建后才能添加
# 暂时注释，等集群部署完成后再通过 Kubernetes Service 自动添加
# resource "alicloud_slb_backend_server" "api" {
#   load_balancer_id = alicloud_slb_load_balancer.main.id
#   backend_servers {
#     server_id = ""  # 将由Kubernetes Service自动添加
#     weight    = 100
#   }
# }

# 后端服务器组 - Web
# resource "alicloud_slb_backend_server" "web" {
#   load_balancer_id = alicloud_slb_load_balancer.main.id
#   backend_servers {
#     server_id = ""  # 将由Kubernetes Service自动添加
#     weight    = 100
#   }
# }

# 监听器 - HTTP (重定向到HTTPS)
resource "alicloud_slb_listener" "http" {
  load_balancer_id    = alicloud_slb_load_balancer.main.id
  backend_port        = 80
  frontend_port       = 80
  protocol            = "http"
  bandwidth           = 10
  sticky_session      = "on"
  sticky_session_type = "insert"
  cookie_timeout      = 86400
  health_check        = "on"
  health_check_type   = "http"
  health_check_uri    = "/health"
  healthy_threshold   = 2
  unhealthy_threshold = 2
  health_check_timeout = 3
  health_check_interval = 5
}

# 监听器 - HTTPS
# 注意：HTTPS 监听器需要证书，暂时注释，等证书配置完成后再启用
# resource "alicloud_slb_listener" "https" {
#   load_balancer_id    = alicloud_slb_load_balancer.main.id
#   backend_port        = 443
#   frontend_port       = 443
#   protocol            = "https"
#   bandwidth           = 10
#   server_certificate_id = alicloud_slb_server_certificate.main.id
#   # 注意：需要先创建证书资源，或通过控制台上传证书后使用证书ID
#   sticky_session      = "on"
#   sticky_session_type = "insert"
#   cookie_timeout      = 86400
#   health_check        = "on"
#   health_check_type   = "http"
#   health_check_uri    = "/health"
#   healthy_threshold   = 2
#   unhealthy_threshold = 2
#   health_check_timeout = 3
#   health_check_interval = 5
# }

# SSL证书（使用 alicloud_slb_server_certificate）
# 注意：证书文件需要预先存在，或通过其他方式上传
# 如果证书文件不存在，可以暂时注释掉此资源，后续通过控制台或API上传证书
# resource "alicloud_slb_server_certificate" "main" {
#   name             = "${var.project_name}-${var.environment}-cert"
#   server_certificate = file("${path.module}/../../certs/server.crt")
#   private_key        = file("${path.module}/../../certs/server.key")
# }

# 输出
output "slb_address" {
  description = "SLB公网IP地址"
  value       = alicloud_slb_load_balancer.main.address
}

output "slb_id" {
  description = "SLB ID"
  value       = alicloud_slb_load_balancer.main.id
}

