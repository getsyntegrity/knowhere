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

provider "alicloud" {
  region     = var.region
  access_key = var.access_key
  secret_key = var.secret_key
}

# 变量定义
variable "region" {
  description = "阿里云区域"
  type        = string
  default     = "cn-hangzhou"
}

variable "access_key" {
  description = "阿里云AccessKey ID"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "阿里云AccessKey Secret"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "环境名称 (dev/test/prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod"
  }
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "knowhere"
}

variable "domain_name" {
  description = "域名"
  type        = string
}

variable "api_webhook_endpoint" {
  description = "API webhook endpoint for OSS events"
  type        = string
  default     = ""
}

# 数据源
data "alicloud_zones" "available" {
  available_resource_creation = "VSwitch"
}

