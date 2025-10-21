# Terraform配置 - AWS EC2 直接部署方案
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 数据源
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# 获取最新的Ubuntu 22.04 LTS AMI
data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# 获取现有VPC（如果存在）
data "aws_vpc" "existing" {
  count = var.use_existing_vpc ? 1 : 0
  id    = var.existing_vpc_id
}

# 获取现有子网（如果存在）
data "aws_subnets" "existing" {
  count = var.use_existing_vpc ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [var.existing_vpc_id]
  }
}

# 获取现有安全组（如果存在）
data "aws_security_group" "existing" {
  count = var.use_existing_security_group ? 1 : 0
  id    = var.existing_security_group_id
}

# 获取现有RDS实例（如果存在）
data "aws_db_instance" "existing" {
  count                  = var.use_existing_rds ? 1 : 0
  db_instance_identifier = var.existing_rds_identifier
}

# 获取现有ElastiCache集群（如果存在）
data "aws_elasticache_replication_group" "existing" {
  count                = var.use_existing_redis ? 1 : 0
  replication_group_id = var.existing_redis_identifier
}

# 获取现有S3存储桶（如果存在）
data "aws_s3_bucket" "existing" {
  count  = var.use_existing_s3 ? 1 : 0
  bucket = var.existing_s3_bucket_name
}
