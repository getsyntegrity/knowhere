# 变量定义

variable "aws_region" {
  description = "AWS区域"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "环境名称"
  type        = string
  default     = "test"
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "knowhere"
}

variable "domain_name" {
  description = "主域名"
  type        = string
  default     = "knowhereto.ai"
}

variable "api_subdomain" {
  description = "API子域名"
  type        = string
  default     = "apitest"
}

variable "web_subdomain" {
  description = "Web子域名"
  type        = string
  default     = "test"
}

# 实例配置
variable "instance_type" {
  description = "EC2实例类型"
  type        = string
  default     = "t3.large"
}

variable "use_existing_instance" {
  description = "是否使用现有EC2实例"
  type        = bool
  default     = false
}

variable "existing_instance_id" {
  description = "现有EC2实例ID"
  type        = string
  default     = ""
}

# Git仓库配置
variable "git_repository_url" {
  description = "Git仓库URL"
  type        = string
  default     = ""
}

variable "git_branch" {
  description = "Git分支名称"
  type        = string
  default     = "main"
}

variable "git_ssh_key_path" {
  description = "Git SSH私钥路径（用于私有仓库）"
  type        = string
  default     = ""
}

variable "root_volume_size" {
  description = "根卷大小（GB）"
  type        = number
  default     = 50
}

variable "root_volume_type" {
  description = "根卷类型"
  type        = string
  default     = "gp3"
}

variable "root_volume_iops" {
  description = "根卷IOPS"
  type        = number
  default     = 3000
}

# 网络配置
variable "use_existing_vpc" {
  description = "是否使用现有VPC"
  type        = bool
  default     = false
}

variable "existing_vpc_id" {
  description = "现有VPC ID"
  type        = string
  default     = ""
}

variable "use_existing_security_group" {
  description = "是否使用现有安全组"
  type        = bool
  default     = false
}

variable "existing_security_group_id" {
  description = "现有安全组ID"
  type        = string
  default     = ""
}

# 数据库配置
variable "use_existing_rds" {
  description = "是否使用现有RDS"
  type        = bool
  default     = false
}

variable "existing_rds_identifier" {
  description = "现有RDS实例标识符"
  type        = string
  default     = ""
}

variable "use_existing_redis" {
  description = "是否使用现有Redis"
  type        = bool
  default     = false
}

variable "existing_redis_identifier" {
  description = "现有Redis集群标识符"
  type        = string
  default     = ""
}

# S3配置
variable "use_existing_s3" {
  description = "是否使用现有S3存储桶"
  type        = bool
  default     = false
}

variable "existing_s3_bucket_name" {
  description = "现有S3存储桶名称"
  type        = string
  default     = ""
}

# 标签
variable "common_tags" {
  description = "通用标签"
  type        = map(string)
  default = {
    Project     = "knowhere"
    Environment = "test"
    ManagedBy   = "terraform"
  }
}

# 密钥配置
variable "key_pair_name" {
  description = "EC2密钥对名称"
  type        = string
  default     = ""
}

variable "create_key_pair" {
  description = "是否创建新的密钥对"
  type        = bool
  default     = true
}

# 监控配置
variable "enable_detailed_monitoring" {
  description = "是否启用详细监控"
  type        = bool
  default     = false
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch日志保留天数"
  type        = number
  default     = 7
}

# 通知配置
variable "notification_email" {
  description = "告警通知邮箱"
  type        = string
  default     = ""
}

# SSL配置
variable "enable_ssl" {
  description = "是否启用SSL"
  type        = bool
  default     = true
}

variable "ssl_certificate_arn" {
  description = "SSL证书ARN（如果使用ACM）"
  type        = string
  default     = ""
}
