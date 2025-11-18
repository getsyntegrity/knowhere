# Terraform配置 - 阿里云ACK容器服务部署
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

# 默认 provider（使用 RAM 用户凭证）
provider "alicloud" {
  region     = var.region
  access_key = var.access_key
  secret_key = var.secret_key
}

# 主账号 provider（用于需要高权限的资源，如 ACK 集群）
# 如果未提供主账号凭证，则使用默认 provider
provider "alicloud" {
  alias      = "master"
  region     = var.region
  access_key = var.master_access_key != "" ? var.master_access_key : var.access_key
  secret_key = var.master_secret_key != "" ? var.master_secret_key : var.secret_key
}

# 变量定义在 variables.tf 中

# 数据源
data "alicloud_zones" "available" {
  available_resource_creation = "VSwitch"
}

