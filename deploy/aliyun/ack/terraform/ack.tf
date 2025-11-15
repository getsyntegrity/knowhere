# ACK集群配置 - 多环境支持
# 使用主账号 provider 以避免权限问题
resource "alicloud_cs_managed_kubernetes" "main" {
  provider = alicloud.master

  name                 = "${var.project_name}-${var.environment}-cluster"
  cluster_spec          = "ack.pro.small"
  version               = "1.28.15-aliyun.1"
  new_nat_gateway       = false
  node_cidr_mask        = 25
  proxy_mode            = "ipvs"
  pod_vswitch_ids       = alicloud_vswitch.private[*].id
  vswitch_ids          = alicloud_vswitch.private[*].id
  slb_internet_enabled  = true
  # 注意：worker_instance_types 和 worker_number 已移除
  # 工作节点配置通过 ack-node-pool.tf 中的 node pool 管理

  # 网络配置（使用新的参数格式）
  pod_cidr          = "172.20.0.0/16"
  service_cidr      = "172.21.0.0/20"

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

