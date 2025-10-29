# ECS实例配置

# 创建密钥对（如果指定）
resource "alicloud_ecs_key_pair" "app_key" {
  count        = var.create_key_pair ? 1 : 0
  key_pair_name = "${var.project_name}-${var.environment}-key"
  public_key    = var.create_key_pair ? file("${path.module}/../scripts/id_rsa.pub") : ""
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-key"
  })
}

# 使用现有ECS实例
data "alicloud_instances" "existing" {
  count       = var.use_existing_instance ? 1 : 0
  instance_ids = [var.existing_instance_id]
}

# 本地值：统一的实例引用
locals {
  instance_id       = var.use_existing_instance ? data.alicloud_instances.existing[0].instances[0].id : alicloud_instance.app_server[0].id
  instance_public_ip  = var.use_existing_instance ? data.alicloud_instances.existing[0].instances[0].public_ip : alicloud_instance.app_server[0].public_ip
  instance_private_ip = var.use_existing_instance ? data.alicloud_instances.existing[0].instances[0].private_ip : alicloud_instance.app_server[0].private_ip
}

# ECS实例（仅在不使用现有实例时创建）
resource "alicloud_instance" "app_server" {
  count                = var.use_existing_instance ? 0 : 1
  instance_name        = "${var.project_name}-${var.environment}-app-server"
  instance_type        = var.instance_type
  image_id             = data.alicloud_images.ubuntu_2204.images[0].id
  security_groups      = [local.app_security_group_id]
  vswitch_id           = var.use_existing_vpc ? data.alicloud_vswitches.existing[0].vswitches[0].id : alicloud_vswitch.public[0].id
  
  # SSH密钥对
  key_name = var.create_key_pair ? alicloud_ecs_key_pair.app_key[0].key_pair_name : var.key_pair_name
  
  # 系统盘配置
  system_disk_category = var.root_volume_type
  system_disk_size     = var.root_volume_size
  
  # 公网IP
  internet_max_bandwidth_out = 10
  internet_charge_type       = "PayByTraffic"
  
  # 用户数据脚本
  user_data = base64encode(templatefile("${path.module}/../user-data/ecs-instance-init.sh", {
    project_name       = var.project_name
    environment        = var.environment
    region             = var.region
    GIT_REPOSITORY_URL = var.git_repository_url
    GIT_BRANCH         = var.git_branch
    GIT_SSH_KEY_PATH   = var.git_ssh_key_path
  }))
  
  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-app-server"
  })
  
  # 依赖关系
  depends_on = [
    alicloud_vpc.main,
    alicloud_security_group.app_server
  ]
}

# 弹性公网IP（可选，用于固定公网IP）
resource "alicloud_eip_address" "app_server" {
  count                = var.use_existing_instance ? 0 : 1
  address_name         = "${var.project_name}-${var.environment}-eip"
  bandwidth            = "10"
  internet_charge_type = "PayByTraffic"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-eip"
  })
}

# 绑定EIP到ECS实例
resource "alicloud_eip_association" "app_server" {
  count         = var.use_existing_instance ? 0 : 1
  allocation_id = alicloud_eip_address.app_server[0].id
  instance_id   = alicloud_instance.app_server[0].id
}

