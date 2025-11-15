# ACK 节点池配置 - 用于管理工作节点
resource "alicloud_cs_kubernetes_node_pool" "main" {
  name                 = "${var.project_name}-${var.environment}-nodepool"
  cluster_id           = alicloud_cs_managed_kubernetes.main.id
  vswitch_ids          = alicloud_vswitch.private[*].id
  instance_types       = var.environment == "prod" ? ["ecs.c7.xlarge"] : ["ecs.c7.large"]
  desired_size         = var.environment == "prod" ? 3 : 2

  # 系统盘配置
  system_disk_category = "cloud_essd"
  system_disk_size     = 40

  # 数据盘配置
  data_disks {
    category = "cloud_essd"
    size     = 100
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

