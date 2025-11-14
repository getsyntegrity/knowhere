# ACK集群配置 - 多环境支持
resource "alicloud_cs_managed_kubernetes" "main" {
  name                 = "${var.project_name}-${var.environment}-cluster"
  cluster_spec          = "ack.pro.small"
  version               = "1.28.15-aliyun.1"
  new_nat_gateway       = false
  node_cidr_mask        = 25
  proxy_mode            = "ipvs"
  service_network_cidr  = "172.21.0.0/20"
  pod_vswitch_ids       = alicloud_vswitch.private[*].id
  worker_vswitch_ids    = alicloud_vswitch.private[*].id
  slb_internet_enabled  = true
  install_cloud_monitor = true

  # 工作节点配置
  worker_instance_types = var.environment == "prod" ? ["ecs.c7.xlarge"] : ["ecs.c7.large"]
  worker_number        = var.environment == "prod" ? 3 : 2
  worker_disk_size     = 40
  worker_disk_category = "cloud_essd"
  worker_data_disk_size = 100

  # 网络配置
  network_plugin    = "terway"
  pod_cidr          = "172.20.0.0/16"
  service_cidr      = "172.21.0.0/20"
  enable_ssh        = true

  # 标签
  tags = {
    Name        = "${var.project_name}-${var.environment}-cluster"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 输出
output "kubeconfig" {
  description = "Kubernetes配置"
  value       = alicloud_cs_managed_kubernetes.main.kube_config
  sensitive   = true
}

output "cluster_id" {
  description = "ACK集群ID"
  value       = alicloud_cs_managed_kubernetes.main.id
}

