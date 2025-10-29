# 阿里云 ECS 部署 Terraform 配置
# 这是从 AWS EC2 迁移到阿里云 ECS 的 Terraform 配置

terraform {
  required_version = ">= 1.0"
  required_providers {
    alicloud = {
      source  = "aliyun/alicloud"
      version = "~> 1.200"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "alicloud" {
  # 从环境变量或变量读取认证信息
  # export ALICLOUD_ACCESS_KEY=xxx
  # export ALICLOUD_SECRET_KEY=xxx
  region     = var.region
  access_key = var.access_key != "" ? var.access_key : null
  secret_key = var.secret_key != "" ? var.secret_key : null
}

# 数据源 - 获取可用区信息
data "alicloud_zones" "available" {
  available_resource_creation = "VSwitch"
}

# 数据源 - 获取可用的镜像
# 查找Ubuntu 22.04镜像
data "alicloud_images" "ubuntu_2204" {
  name_regex  = "^ubuntu_22_04_64"
  owners      = "system"
  most_recent = true
}

# 获取现有VPC（如果存在）
data "alicloud_vpcs" "existing" {
  count = var.use_existing_vpc ? 1 : 0
  ids   = [var.existing_vpc_id]
}

# 获取现有VSwitch（如果存在）
data "alicloud_vswitches" "existing" {
  count  = var.use_existing_vpc ? 1 : 0
  vpc_id = var.existing_vpc_id
}

# 获取现有安全组（如果存在）
data "alicloud_security_groups" "existing" {
  count = var.use_existing_security_group ? 1 : 0
  ids   = [var.existing_security_group_id]
}

# 获取现有RDS实例（如果存在）
data "alicloud_db_instances" "existing" {
  count = var.use_existing_rds ? 1 : 0
  ids   = [var.existing_rds_instance_id]
}

# 获取现有Redis实例（如果存在）
data "alicloud_kvstore_instances" "existing" {
  count = var.use_existing_redis ? 1 : 0
  ids   = [var.existing_redis_instance_id]
}

# 获取现有OSS存储桶（如果存在）
data "alicloud_oss_buckets" "existing" {
  count     = var.use_existing_oss ? 1 : 0
  name_regex = var.existing_oss_bucket_name
}
