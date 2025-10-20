# AWS ECS Fargate 部署指南

本指南将帮助你使用AWS ECS Fargate部署Knowhere知识库管理系统。

## 架构概览

```
Internet
    ↓
Route 53 (DNS)
    ↓
Application Load Balancer (ALB)
    ↓
┌─────────────────┬─────────────────┐
│   Frontend      │   Backend       │
│   (Next.js)     │   (FastAPI)     │
│   ECS Fargate   │   ECS Fargate   │
└─────────────────┴─────────────────┘
    ↓                     ↓
    └─────────┬───────────┘
              ↓
    ┌─────────────────────────┐
    │   RDS PostgreSQL        │
    │   ElastiCache Redis     │
    │   S3 Storage            │
    └─────────────────────────┘
```

## 前置要求

### 1. AWS账户和权限
- AWS账户
- 具有以下权限的IAM用户或角色：
  - ECS Full Access
  - EC2 Full Access
  - RDS Full Access
  - ElastiCache Full Access
  - S3 Full Access
  - IAM Full Access
  - Route53 Full Access
  - ACM Full Access

### 2. 本地工具
- AWS CLI v2
- Terraform >= 1.0
- Docker
- Git
- jq (JSON处理工具)

### 3. 域名
- 一个已注册的域名
- 域名在Route53中托管（或可以配置NS记录）

## 部署步骤

### 第一步：准备环境

1. **克隆项目**
```bash
git clone <your-repo-url>
cd knowhere
```

2. **安装AWS CLI**
```bash
# macOS
brew install awscli

# 或使用pip
pip install awscli
```

3. **配置AWS凭证**
```bash
aws configure
# 输入你的Access Key ID和Secret Access Key
```

4. **安装Terraform**
```bash
# macOS
brew install terraform

# 或下载二进制文件
wget https://releases.hashicorp.com/terraform/1.5.0/terraform_1.5.0_darwin_amd64.zip
unzip terraform_1.5.0_darwin_amd64.zip
sudo mv terraform /usr/local/bin/
```

### 第二步：配置Terraform

1. **复制配置文件**
```bash
cd deploy/aws/terraform
cp terraform.tfvars.example terraform.tfvars
```

2. **编辑terraform.tfvars**
```bash
# 填入你的实际配置
aws_region = "us-east-1"
project_name = "knowhere"
environment = "production"
domain_name = "yourdomain.com"
db_password = "your-secure-password"
```

### 第三步：部署基础设施

1. **初始化Terraform**
```bash
cd deploy/aws/terraform
terraform init
```

2. **规划部署**
```bash
terraform plan
```

3. **应用配置**
```bash
terraform apply
```

这将创建：
- VPC和子网
- 安全组
- RDS PostgreSQL数据库
- ElastiCache Redis
- S3存储桶
- ECS集群
- 应用负载均衡器
- Route53记录

### 第四步：构建和推送Docker镜像

1. **设置环境变量**
```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
export PROJECT_NAME=knowhere
```

2. **构建和推送镜像**
```bash
# 构建并推送镜像
./deploy/aws/scripts/build-and-push.sh

# 或者构建并部署
./deploy/aws/scripts/build-and-push.sh --deploy
```

### 第五步：部署ECS服务

1. **运行部署脚本**
```bash
./deploy/aws/scripts/deploy.sh all
```

这将：
- 创建ECS任务定义
- 创建ECS服务
- 等待服务稳定

### 第六步：配置环境变量

1. **获取数据库连接信息**
```bash
cd deploy/aws/terraform
terraform output
```

2. **在AWS Secrets Manager中创建密钥**
```bash
# 数据库URL
aws secretsmanager create-secret \
  --name "knowhere/database-url" \
  --secret-string "postgresql+asyncpg://postgres:your-password@your-rds-endpoint:5432/knowhere"

# Redis主机
aws secretsmanager create-secret \
  --name "knowhere/redis-host" \
  --secret-string "your-redis-endpoint"

# 其他密钥...
```

## 环境变量配置

### 后端环境变量
在ECS任务定义中配置以下环境变量：

```json
{
  "environment": [
    {"name": "ENVIRONMENT", "value": "production"},
    {"name": "DEBUG", "value": "false"},
    {"name": "LOG_LEVEL", "value": "INFO"}
  ],
  "secrets": [
    {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:region:account:secret:knowhere/database-url"},
    {"name": "REDIS_HOST", "valueFrom": "arn:aws:secretsmanager:region:account:secret:knowhere/redis-host"},
    {"name": "S3_ACCESS_KEY_ID", "valueFrom": "arn:aws:secretsmanager:region:account:secret:knowhere/s3-access-key"},
    {"name": "S3_SECRET_ACCESS_KEY", "valueFrom": "arn:aws:secretsmanager:region:account:secret:knowhere/s3-secret-key"},
    {"name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:region:account:secret:knowhere/secret-key"}
  ]
}
```

### 前端环境变量
```json
{
  "environment": [
    {"name": "NODE_ENV", "value": "production"},
    {"name": "NEXT_PUBLIC_API_URL", "value": "https://api.yourdomain.com"},
    {"name": "NEXT_PUBLIC_POSTHOG_KEY", "value": "phc_xxx"}
  ]
}
```

## 监控和日志

### CloudWatch日志
- 后端日志：`/ecs/knowhere-backend`
- 前端日志：`/ecs/knowhere-frontend`

### 健康检查
- 后端：`https://api.yourdomain.com/health`
- 前端：`https://yourdomain.com/`

### 监控指标
- ECS服务指标
- ALB指标
- RDS指标
- ElastiCache指标

## 故障排除

### 常见问题

1. **服务无法启动**
   - 检查任务定义中的环境变量
   - 查看CloudWatch日志
   - 验证安全组配置

2. **数据库连接失败**
   - 检查RDS安全组
   - 验证数据库密码
   - 确认子网配置

3. **镜像拉取失败**
   - 检查ECR权限
   - 验证镜像标签
   - 确认网络连接

### 调试命令

```bash
# 查看ECS服务状态
aws ecs describe-services --cluster knowhere-cluster --services knowhere-backend-service

# 查看任务日志
aws logs get-log-events --log-group-name /ecs/knowhere-backend --log-stream-name <stream-name>

# 进入容器调试
aws ecs execute-command --cluster knowhere-cluster --task <task-arn> --container knowhere-backend --interactive --command "/bin/bash"
```

## 成本优化

### 资源大小建议
- **后端**: 1 vCPU, 2GB RAM (可根据负载调整)
- **前端**: 0.5 vCPU, 1GB RAM
- **数据库**: db.t3.micro (开发) / db.t3.small (生产)
- **Redis**: cache.t3.micro

### 成本监控
- 使用AWS Cost Explorer
- 设置预算告警
- 定期审查资源使用情况

## 安全最佳实践

1. **网络安全**
   - 使用私有子网部署数据库
   - 配置安全组最小权限
   - 启用VPC Flow Logs

2. **数据安全**
   - 启用数据库加密
   - 使用AWS Secrets Manager
   - 定期轮换密钥

3. **应用安全**
   - 使用HTTPS
   - 配置WAF
   - 定期更新依赖

## 扩展和维护

### 自动扩缩容
```bash
# 配置ECS服务自动扩缩容
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/knowhere-cluster/knowhere-backend-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 10
```

### 更新部署
```bash
# 更新镜像
./deploy/aws/scripts/build-and-push.sh --deploy

# 或使用GitHub Actions自动部署
git push origin main
```

### 备份策略
- RDS自动备份
- S3版本控制
- 定期快照

## 支持

如果遇到问题，请：
1. 查看CloudWatch日志
2. 检查AWS服务状态
3. 参考AWS文档
4. 联系技术支持

---

**注意**: 这是一个生产级别的部署配置，请根据实际需求调整资源大小和配置参数。
