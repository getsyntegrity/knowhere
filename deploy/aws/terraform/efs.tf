# EFS文件系统 - 用于模型缓存共享存储
resource "aws_efs_file_system" "model_cache" {
  creation_token = "${var.project_name}-${var.environment}-model-cache"
  
  performance_mode = "generalPurpose"
  throughput_mode  = "provisioned"
  provisioned_throughput_in_mibps = 100

  encrypted = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-model-cache"
    Environment = var.environment
    Project     = var.project_name
  }
}

# EFS挂载目标 - 在每个私有子网中创建
resource "aws_efs_mount_target" "model_cache" {
  count = length(aws_subnet.private)

  file_system_id  = aws_efs_file_system.model_cache.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# EFS安全组
resource "aws_security_group" "efs" {
  name_prefix = "${var.project_name}-${var.environment}-efs-"
  vpc_id      = aws_vpc.main.id
  description = "Security group for EFS model cache"

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
    description     = "NFS access from ECS tasks"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-efs-sg"
    Environment = var.environment
  }
}

# 输出
output "efs_file_system_id" {
  description = "EFS文件系统ID"
  value       = aws_efs_file_system.model_cache.id
}

output "efs_dns_name" {
  description = "EFS DNS名称"
  value       = "${aws_efs_file_system.model_cache.id}.efs.${var.aws_region}.amazonaws.com"
}

