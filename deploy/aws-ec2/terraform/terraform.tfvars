# Terraform变量配置文件示例
# 复制此文件为 terraform.tfvars 并填入实际值

# AWS配置
aws_region = "us-west-1"

# 项目配置
project_name = "knowhere"
environment  = "test"
domain_name  = "knowhereto.ai"

# 子域名配置
api_subdomain = "apitest"
web_subdomain = "test"

# 实例配置
instance_type        = "m7i-flex.large"
use_existing_instance = true
existing_instance_id  = "i-0c9b2ba8283e18b71"  # 手动创建的实例ID
root_volume_size     = 50
root_volume_type     = "gp3"
root_volume_iops     = 3000

# 网络配置（使用现有资源）
use_existing_vpc              = true
existing_vpc_id               = "vpc-09f6daf4d60f2eb0b"
use_existing_security_group   = true
existing_security_group_id    = "sg-00db88058f5db1270"

# 数据库配置（使用现有资源）
use_existing_rds              = true
existing_rds_identifier       = "database-test"
use_existing_redis            = true
existing_redis_identifier     = "knowhere-test-redis"

# S3配置（使用现有资源）
use_existing_s3               = true
existing_s3_bucket_name       = "knowhere-api-dev"

# 密钥配置
create_key_pair = false
key_pair_name   = "Knowhere-Test"

# Git仓库配置
git_repository_url = "https://gitee.com/ono_road_i/knowhereapi.git"  # 请替换为实际的仓库URL
git_branch         = "main"
git_ssh_key_path   = "/opt/knowhere/deploy/aws-ec2/scripts/repo-git"  # SSH私钥路径

# 监控配置
enable_detailed_monitoring     = false
cloudwatch_log_retention_days = 7
notification_email            = ""

# SSL配置
enable_ssl            = false
ssl_certificate_arn   = ""

# 标签
common_tags = {
  Project     = "knowhere"
  Environment = "test"
  ManagedBy   = "terraform"
  Owner       = "knowhere-ai"
}
