# EC2实例配置

# 创建密钥对（如果指定）
resource "aws_key_pair" "app_key" {
  count      = var.create_key_pair ? 1 : 0
  key_name   = "${var.project_name}-${var.environment}-key"
  public_key = var.create_key_pair ? file("${path.module}/../scripts/id_rsa.pub") : ""

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-key"
  })
}

# 使用现有密钥对
data "aws_key_pair" "existing" {
  count    = var.create_key_pair ? 0 : 1
  key_name = var.key_pair_name
}

# 使用现有EC2实例
data "aws_instance" "existing" {
  count       = var.use_existing_instance ? 1 : 0
  instance_id = var.existing_instance_id
}

# 本地值：统一的实例引用
locals {
  instance_id = var.use_existing_instance ? data.aws_instance.existing[0].id : aws_instance.app_server[0].id
  instance_public_ip = var.use_existing_instance ? data.aws_instance.existing[0].public_ip : aws_instance.app_server[0].public_ip
  instance_private_ip = var.use_existing_instance ? data.aws_instance.existing[0].private_ip : aws_instance.app_server[0].private_ip
  instance_public_dns = var.use_existing_instance ? data.aws_instance.existing[0].public_dns : aws_instance.app_server[0].public_dns
}

# EC2实例（仅在不使用现有实例时创建）
resource "aws_instance" "app_server" {
  count                  = var.use_existing_instance ? 0 : 1
  ami                    = data.aws_ami.ubuntu_2204.id
  instance_type          = var.instance_type
  key_name               = var.create_key_pair ? aws_key_pair.app_key[0].key_name : data.aws_key_pair.existing[0].key_name
  vpc_security_group_ids = [var.use_existing_security_group ? var.existing_security_group_id : aws_security_group.app_server[0].id]
  subnet_id              = var.use_existing_vpc ? data.aws_subnets.existing[0].ids[0] : aws_subnet.public[0].id

  root_block_device {
    volume_type           = var.root_volume_type
    volume_size           = var.root_volume_size
    iops                  = var.root_volume_iops
    delete_on_termination = true
    encrypted             = true

    tags = merge(var.common_tags, {
      Name = "${var.project_name}-${var.environment}-root-volume"
    })
  }

  # 启用详细监控
  monitoring = var.enable_detailed_monitoring

  # IAM实例配置文件
  iam_instance_profile = aws_iam_instance_profile.app_server.name

  # 用户数据脚本
  user_data = base64encode(templatefile("${path.module}/../user-data/ecs-instance-init.sh", {
    project_name        = var.project_name
    environment         = var.environment
    region              = var.aws_region
    GIT_REPOSITORY_URL  = var.git_repository_url
    GIT_BRANCH          = var.git_branch
    GIT_SSH_KEY_PATH    = var.git_ssh_key_path
  }))

  # 标签
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-app-server"
  })

  # 生命周期管理
  lifecycle {
    create_before_destroy = true
  }

  # 依赖关系
  depends_on = [
    aws_iam_instance_profile.app_server,
    aws_cloudwatch_log_group.app_logs
  ]
}

# 弹性IP（可选，用于固定公网IP）
resource "aws_eip" "app_server" {
  count    = var.enable_detailed_monitoring ? 1 : 0
  instance = local.instance_id
  domain   = "vpc"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-eip"
  })

  # depends_on will be handled by the instance reference
}

# 实例保护（防止意外终止）
# 注意：disable_api_termination 应该在 aws_instance 资源中配置
