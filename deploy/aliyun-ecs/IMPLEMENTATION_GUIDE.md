# 阿里云ECS迁移实施指南

## 快速对比表

### AWS vs 阿里云服务映射

| 组件 | AWS | 阿里云 | 对应关系 |
|------|-----|--------|----------|
| 虚拟服务器 | EC2 | ECS | 1:1映射，配置略有不同 |
| 专用网络 | VPC | VPC专有网络 | 1:1映射，概念相同 |
| 子网 | Subnet | VSwitch交换机 | 1:1映射，名称不同 |
| 公网IP | Elastic IP | EIP弹性公网IP | 1:1映射 |
| 安全组 | Security Group | 安全组 | 1:1映射，规则语法不同 |
| 路由表 | Route Table | 路由表 | 相似 |
| 网络地址转换 | NAT Gateway | NAT网关 | 相似 |
| 关系数据库 | RDS PostgreSQL | RDS PostgreSQL | 高度兼容 |
| 缓存服务 | ElastiCache Redis | ApsaraDB Redis | 高度兼容 |
| 对象存储 | S3 | OSS | API不同，需改代码 |
| 负载均衡 | Application Load Balancer | SLB | 概念相似 |
| 监控服务 | CloudWatch | 云监控 | 功能相似 |
| 日志服务 | CloudWatch Logs | 日志服务SLS | 功能相似 |
| 证书服务 | ACM | SSL证书 | 概念相同 |
| 密钥管理 | Secrets Manager | Secrets Manager | 概念相同 |

## 关键技术调整点

### 1. Terraform Provider变更

#### AWS配置
```hcl
terraform {
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
```

#### 阿里云配置
```hcl
terraform {
  required_providers {
    alicloud = {
      source  = "aliyun/alicloud"
      version = "~> 1.200"
    }
  }
}

provider "alicloud" {
  region     = var.region
  access_key = var.access_key
  secret_key = var.secret_key
}
```

### 2. 网络配置调整

#### VPC和子网

**AWS (aws-ec2/terraform/vpc.tf)**:
```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}
```

**阿里云等价配置**:
```hcl
resource "alicloud_vpc" "main" {
  vpc_name   = "${var.project_name}-vpc"
  cidr_block  = "10.0.0.0/16"
  
  # DNS配置在VPC级别
  enable_ipv6 = false
}

resource "alicloud_vswitch" "public" {
  vpc_id      = alicloud_vpc.main.id
  cidr_block  = "10.0.1.0/24"
  zone_id     = "cn-hangzhou-b" # 可用区
  vswitch_name = "${var.project_name}-public-vswitch"
}
```

### 3. 安全组规则调整

#### AWS安全组
```hcl
resource "aws_security_group" "app_server" {
  vpc_id = aws_vpc.main.id
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

#### 阿里云安全组
```hcl
resource "alicloud_security_group" "app_server" {
  name        = "${var.project_name}-app-sg"
  vpc_id      = alicloud_vpc.main.id
  description = "Security group for app servers"
}

resource "alicloud_security_group_rule" "http_ingress" {
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "internet"
  policy            = "accept"
  port_range        = "80/80"
  priority          = 1
  security_group_id = alicloud_security_group.app_server.id
  cidr_ip           = "0.0.0.0/0"
}
```

### 4. ECS实例配置

#### AWS EC2
```hcl
resource "aws_instance" "app_server" {
  ami           = data.aws_ami.ubuntu_2204.id
  instance_type = "t3.large"
  key_name      = aws_key_pair.app_key.key_name
  vpc_security_group_ids = [aws_security_group.app_server.id]
  subnet_id     = aws_subnet.public.id
}
```

#### 阿里云ECS
```hcl
resource "alicloud_instance" "app_server" {
  instance_name  = "${var.project_name}-app"
  instance_type  = "ecs.c7.large" # 2核4G
  image_id       = data.alicloud_images.ubuntu.images[0].id
  security_groups = [alicloud_security_group.app_server.id]
  vswitch_id     = alicloud_vswitch.public.id
  
  # SSH密钥对
  key_name       = alicloud_ecs_key_pair.app_key.key_pair_name
  
  # 系统盘配置
  system_disk_category = "cloud_essd"
  system_disk_size     = 50
}
```

### 5. 数据库配置调整

#### AWS RDS
```hcl
resource "aws_db_instance" "main" {
  identifier     = "${var.project_name}-db"
  engine         = "postgres"
  engine_version = "15.7"
  instance_class = "db.t3.micro"
  allocated_storage = 20
  
  db_subnet_group_name = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
}
```

#### 阿里云RDS
```hcl
resource "alicloud_db_instance" "main" {
  engine           = "PostgreSQL"
  engine_version   = "15.0"
  instance_type    = "pg.n2.medium.1"
  instance_storage = 20
  instance_name    = "${var.project_name}-db"
  
  vpc_id    = alicloud_vpc.main.id
  vswitch_id = alicloud_vswitch.private.id
  
  security_ips = [alicloud_vswitch.private.cidr_block]
}
```

### 6. 对象存储调整

#### AWS S3 → 阿里云OSS

**AWS配置**:
```python
import boto3

s3_client = boto3.client('s3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name='us-east-1'
)

s3_client.upload_fileobj(file_obj, bucket_name, object_name)
```

**阿里云配置**:
```python
from oss2 import Auth, Bucket, Session

# OSS配置
auth = Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_SECRET_ACCESS_KEY)
bucket = Bucket(auth, endpoint, bucket_name)

# 上传文件
bucket.put_object(object_name, file_obj)
```

**Terraform配置**:
```hcl
# AWS S3
resource "aws_s3_bucket" "main" {
  bucket = "my-bucket"
  tags = var.common_tags
}

# 阿里云OSS
resource "alicloud_oss_bucket" "main" {
  bucket = "my-bucket"
  acl    = "private"
  tags = var.common_tags
}
```

### 7. CLI工具替换

#### AWS CLI命令
```bash
# 查询实例
aws ec2 describe-instances

# 查看日志
aws logs get-log-events --log-group-name /aws/ec2/knowhere

# 存储桶操作
aws s3 ls
aws s3 cp file.txt s3://my-bucket/
```

#### 阿里云CLI命令
```bash
# 查询实例
aliyun ecs DescribeInstances --RegionId cn-hangzhou

# 查看日志（通过控制台或CLI）
aliyun log GetLogs

# OSS操作
aliyun oss ls
aliyun oss cp file.txt oss://my-bucket/
```

### 8. 监控配置调整

#### AWS CloudWatch
```python
import boto3

cloudwatch = boto3.client('cloudwatch')
cloudwatch.put_metric_data(
    Namespace='Knowhere',
    MetricData=[
        {
            'MetricName': 'RequestCount',
            'Value': count,
            'Unit': 'Count'
        }
    ]
)
```

#### 阿里云监控
```python
from aliyunsdkcore.client import AcsClient
from aliyunsdkcms.request.v20190101 import PutMetricDataRequest

client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, REGION)
request = PutMetricDataRequest.PutMetricDataRequest()
request.set_MetricName('RequestCount')
request.set_Value(count)
client.do_action_with_exception(request)
```

### 9. 环境变量变更

#### AWS环境变量
```bash
# .env
DATABASE_URL=postgresql://user:pass@xxx.rds.amazonaws.com:5432/knowhere
REDIS_HOST=xxx.cache.amazonaws.com
REDIS_PORT=6379
S3_BUCKET_NAME=my-bucket
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
```

#### 阿里云环境变量
```bash
# .env
DATABASE_URL=postgresql://user:pass@xxx.rds.aliyuncs.com:5432/knowhere
REDIS_HOST=xxx.redis.aliyuncs.com
REDIS_PORT=6379
OSS_BUCKET_NAME=my-bucket
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_ACCESS_KEY_ID=xxx
OSS_SECRET_ACCESS_KEY=xxx
```

### 10. 脚本调整要点

#### 部署脚本调整

**provision-instance.sh**:
- ✅ 基本不需要改动（Linux通用）
- ⚠️ 需要调整软件源（如果是国内使用）
- ⚠️ 需要调整时区设置
- ✅ Systemd配置无需改动

**deploy-app.sh**:
- ⚠️ Git SSH配置保持不变
- ⚠️ 依赖安装方式相同
- ✅ 服务管理命令相同

**health-check.sh**:
- ✅ 健康检查逻辑不变
- ⚠️ 如果使用监控系统，需要调整API调用

## 实施步骤详解

### 阶段1: 基础设施准备

#### 1.1 创建Terraform目录结构
```bash
cd deploy
mkdir -p aliyun-ecs/terraform
cd aliyun-ecs/terraform
```

#### 1.2 初始化Terraform
```bash
# 创建main.tf
cat > main.tf << 'EOF'
terraform {
  required_version = ">= 1.0"
  required_providers {
    alicloud = {
      source  = "aliyun/alicloud"
      version = "~> 1.200"
    }
  }
}

provider "alicloud" {
  region     = "cn-hangzhou"
  access_key = var.access_key
  secret_key = var.secret_key
}
EOF

# 初始化
terraform init
```

### 阶段2: 代码修改

#### 2.1 应用层代码修改

**需要修改的文件** (`apps/api/core/storage.py`):
```python
# 原AWS S3代码
import boto3
s3_client = boto3.client('s3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)

# 修改为阿里云OSS
import oss2
auth = oss2.Auth(
    os.getenv('OSS_ACCESS_KEY_ID'),
    os.getenv('OSS_SECRET_ACCESS_KEY')
)
bucket = oss2.Bucket(auth, 
    os.getenv('OSS_ENDPOINT'),
    os.getenv('OSS_BUCKET_NAME')
)
```

#### 2.2 配置文件修改

**apps/api/.env**:
```bash
# AWS版本
DATABASE_URL=postgresql://user:pass@xxx.rds.amazonaws.com:5432/knowhere
REDIS_HOST=xxx.cache.amazonaws.com
S3_BUCKET_NAME=my-bucket
AWS_REGION=us-east-1

# 阿里云版本
DATABASE_URL=postgresql://user:pass@xxx.rds.aliyuncs.com:5432/knowhere
REDIS_HOST=xxx.redis.aliyuncs.com
OSS_BUCKET_NAME=my-bucket
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
```

### 阶段3: 部署步骤

#### 3.1 基础设施部署
```bash
cd deploy/aliyun-ecs/terraform

# 配置变量
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars

# 部署
terraform init
terraform plan
terraform apply
```

#### 3.2 应用部署
```bash
# SSH到服务器
ssh root@<ecs-public-ip>

# 克隆代码
cd /opt
git clone <repository-url> knowhere

# 运行配置脚本
sudo /opt/knowhere/deploy/aliyun-ecs/scripts/provision-instance.sh

# 配置环境变量
nano /opt/knowhere/.env

# 启动服务
sudo systemctl start knowhere-api
sudo systemctl start knowhere-web
sudo systemctl start knowhere-worker
```

### 阶段4: 验证和测试

#### 4.1 功能验证
```bash
# API健康检查
curl https://apitest.knowhereto.ai/health

# Web页面访问
curl https://test.knowhereto.ai

# 查看服务状态
sudo systemctl status knowhere-api
sudo systemctl status knowhere-web
sudo systemctl status knowhere-worker

# 查看日志
sudo journalctl -u knowhere-api -f
```

#### 4.2 性能测试
```bash
# API性能测试
ab -n 1000 -c 10 https://apitest.knowhereto.ai/api/v1/kbs

# 数据库连接测试
psql $DATABASE_URL -c "SELECT version();"

# Redis连接测试
redis-cli -h $REDIS_HOST -p 6379 ping
```

## 常见问题

### Q1: 为什么选择ECS而不是容器化？
A: 当前AWS EC2方案是直接部署，目的是保持一致性。ECS支持Docker但会增加复杂度。

### Q2: 数据库迁移怎么办？
A: 可以使用`pg_dump`和`pg_restore`进行数据迁移，或者使用AWS DMS/阿里云DTS。

### Q3: OSS和S3 API兼容性？
A: 不兼容，需要修改代码。但可以使用`s3fs-fuse`或`ossfs`挂载OSS。

### Q4: 监控告警如何配置？
A: 使用阿里云云监控配置ECS、RDS、Redis的监控指标和告警规则。

### Q5: 成本对比？
A: 阿里云通常比AWS便宜20-30%，而且有更多本地化优势。

## 下一步行动

1. ✅ 创建阿里云ECS目录结构
2. 🔲 编写Terraform配置文件
3. 🔲 调整部署脚本
4. 🔲 修改应用代码（主要是OSS部分）
5. 🔲 配置监控和告警
6. 🔲 测试环境部署验证
7. 🔲 文档完善

---

**准备时间**: 2-3天
**部署时间**: 1天
**总耗时**: 3-4天

