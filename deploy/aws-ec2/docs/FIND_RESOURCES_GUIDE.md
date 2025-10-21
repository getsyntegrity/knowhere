# 查找现有AWS资源ID指南

本指南将帮助您找到现有AWS资源的ID信息，以便在 `terraform.tfvars` 文件中配置使用现有资源。

## 🚀 快速开始

### 方法1: 使用自动化脚本（推荐）

```bash
# 进入脚本目录
cd deploy/aws-ec2/scripts

# 交互式查找所有资源
./find-existing-resources.sh --interactive

# 或者显示所有资源（不交互）
./find-existing-resources.sh --all
```

### 方法2: 手动查找

#### 1. 查找VPC ID

```bash
# 列出所有VPC
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0],CidrBlock,State]' --output table

# 查找默认VPC
aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text
```

**示例输出：**
```
|  DescribeVpcs  |
|  vpc-12345678  |  default  |  172.31.0.0/16  |  available  |
|  vpc-87654321  |  my-vpc   |  10.0.0.0/16    |  available  |
```

#### 2. 查找安全组ID

```bash
# 列出所有安全组
aws ec2 describe-security-groups --query 'SecurityGroups[*].[GroupId,GroupName,Description,VpcId]' --output table

# 查找特定VPC的安全组
aws ec2 describe-security-groups --filters "Name=vpc-id,Values=vpc-12345678" --query 'SecurityGroups[*].[GroupId,GroupName,Description]' --output table
```

**示例输出：**
```
|  DescribeSecurityGroups  |
|  sg-12345678  |  default  |  default VPC security group  |  vpc-12345678  |
|  sg-87654321  |  web-sg   |  Web server security group   |  vpc-12345678  |
```

#### 3. 查找RDS实例标识符

```bash
# 列出所有RDS实例
aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier,Engine,EngineVersion,DBInstanceClass,DBInstanceStatus,Endpoint.Address]' --output table
```

**示例输出：**
```
|  DescribeDBInstances  |
|  my-postgres-db  |  postgres  |  15.4  |  db.t3.micro  |  available  |  my-postgres-db.abc123.us-east-1.rds.amazonaws.com  |
```

#### 4. 查找Redis集群标识符

```bash
# 列出所有Redis集群
aws elasticache describe-replication-groups --query 'ReplicationGroups[*].[ReplicationGroupId,Description,Status,NodeType,Engine,EngineVersion]' --output table
```

**示例输出：**
```
|  DescribeReplicationGroups  |
|  my-redis-cluster  |  Redis cluster for my app  |  available  |  cache.t3.micro  |  redis  |  7.0  |
```

#### 5. 查找S3存储桶名称

```bash
# 列出所有S3存储桶
aws s3api list-buckets --query 'Buckets[*].[Name,CreationDate]' --output table
```

**示例输出：**
```
|  ListBuckets  |
|  my-app-bucket-123456789  |  2024-01-15T10:30:00.000Z  |
|  my-backup-bucket         |  2024-01-20T14:45:00.000Z  |
```

## 📝 配置 terraform.tfvars

找到资源ID后，更新 `terraform.tfvars` 文件：

```hcl
# 网络配置（使用现有资源）
use_existing_vpc              = true
existing_vpc_id               = "vpc-12345678"
use_existing_security_group   = true
existing_security_group_id    = "sg-12345678"

# 数据库配置（使用现有资源）
use_existing_rds              = true
existing_rds_identifier       = "my-postgres-db"
use_existing_redis            = true
existing_redis_identifier     = "my-redis-cluster"

# S3配置（使用现有资源）
use_existing_s3               = true
existing_s3_bucket_name       = "my-app-bucket-123456789"
```

## 🔍 脚本使用选项

### 基本用法

```bash
# 显示帮助
./find-existing-resources.sh --help

# 交互式选择（推荐）
./find-existing-resources.sh --interactive

# 显示所有资源
./find-existing-resources.sh --all

# 指定区域
./find-existing-resources.sh --region us-west-2 --interactive
```

### 查找特定资源类型

```bash
# 只查找VPC
./find-existing-resources.sh --vpc-only

# 只查找安全组
./find-existing-resources.sh --sg-only

# 只查找RDS实例
./find-existing-resources.sh --rds-only

# 只查找Redis集群
./find-existing-resources.sh --redis-only

# 只查找S3存储桶
./find-existing-resources.sh --s3-only
```

## ⚠️ 重要注意事项

### 1. 资源兼容性检查

**VPC要求：**
- 确保VPC有足够的子网（至少2个）
- 子网应该分布在不同的可用区
- 检查VPC的CIDR块是否与您的应用兼容

**安全组要求：**
- 确保安全组允许以下端口：
  - 22 (SSH)
  - 80 (HTTP)
  - 443 (HTTPS)
  - 5005 (API)
  - 3000 (Web)

**数据库要求：**
- RDS实例应该是PostgreSQL 15.x或更高版本
- Redis集群应该是Redis 7.x或更高版本
- 确保数据库在正确的VPC中

### 2. 权限要求

确保您的AWS凭证有权限访问以下服务：
- EC2 (VPC, 安全组)
- RDS (数据库实例)
- ElastiCache (Redis集群)
- S3 (存储桶)

### 3. 区域一致性

确保所有资源都在同一个AWS区域中，避免跨区域访问问题。

## 🛠️ 故障排除

### 常见问题

1. **"未找到资源"**
   - 检查AWS区域设置
   - 确认资源确实存在
   - 检查AWS凭证权限

2. **"权限不足"**
   - 运行 `aws sts get-caller-identity` 检查身份
   - 确保有相应的IAM权限

3. **"资源不可用"**
   - 检查资源状态是否为 "available"
   - 避免使用正在创建或删除中的资源

### 验证资源

```bash
# 验证VPC
aws ec2 describe-vpcs --vpc-ids vpc-12345678

# 验证安全组
aws ec2 describe-security-groups --group-ids sg-12345678

# 验证RDS实例
aws rds describe-db-instances --db-instance-identifier my-postgres-db

# 验证Redis集群
aws elasticache describe-replication-groups --replication-group-id my-redis-cluster

# 验证S3存储桶
aws s3api head-bucket --bucket my-app-bucket-123456789
```

## 📚 相关文档

- [AWS CLI 配置指南](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html)
- [Terraform AWS Provider 文档](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS 资源命名约定](https://docs.aws.amazon.com/general/latest/gr/aws_tagging.html)

---

**💡 提示：** 建议在生产环境中使用现有资源，可以节省成本并保持基础设施的一致性。
