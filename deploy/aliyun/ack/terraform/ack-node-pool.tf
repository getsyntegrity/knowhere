# ACK 节点池配置 - 用于管理工作节点
resource "alicloud_cs_kubernetes_node_pool" "main" {
  name                 = "${var.project_name}-${var.environment}-nodepool"
  cluster_id           = alicloud_cs_managed_kubernetes.main.id
  vswitch_ids          = alicloud_vswitch.private[*].id
  instance_types       = var.environment == "prod" ? ["ecs.g6.xlarge"] : ["ecs.g6.large"]
  desired_size         = 2  # 默认2个节点

  # 系统盘配置
  system_disk_category = "cloud_essd"
  system_disk_size     = 40

  # 数据盘配置
  data_disks {
    category = "cloud_essd"
    size     = 100
  }

  # 自动伸缩配置
  # 临时固定为2个节点，等Pod分布完成后再调整回max_size=10
  scaling_config {
    min_size = 2   # 最小节点数
    max_size = 2   # 最大节点数（临时固定，防止自动扩容）
    # 缩容策略：节点利用率低于30%时考虑缩容
    scale_down_utilization_threshold = "0.3"
  }

  # 云监控
  install_cloud_monitor = true

  # 节点标签
  tags = {
    Name        = "${var.project_name}-${var.environment}-nodepool"
    Environment = var.environment
    Project     = var.project_name
  }
}

