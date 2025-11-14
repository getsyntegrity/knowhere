# 容器化部署指南

本文档描述了Knowhere项目的完整容器化部署方案，支持AWS ECS Fargate和阿里云ACK（容器服务）。

## 架构概述

项目采用统一的容器化部署方式，使用Serverless基础设施服务：

- **计算**: AWS ECS Fargate / 阿里云ACK Kubernetes（容器化）
- **数据库**: AWS RDS Serverless v2 / 阿里云RDS Serverless（PostgreSQL）
- **缓存**: AWS ElastiCache Serverless / 阿里云Redis Serverless
- **消息队列**: AWS Amazon MQ for RabbitMQ / 阿里云云消息队列RabbitMQ版Serverless
- **存储**: AWS S3 / 阿里云OSS（已Serverless）

## 目录结构

```
deploy/
├── docker/                    # 统一Dockerfile目录
│   ├── Dockerfile.api         # API服务Dockerfile
│   ├── Dockerfile.worker      # Worker服务Dockerfile
│   ├── Dockerfile.web         # Web服务Dockerfile
│   └── .dockerignore          # Docker忽略文件
├── aws/                       # AWS部署配置
│   ├── terraform/             # Terraform基础设施配置
│   │   ├── main.tf            # 主配置
│   │   ├── vpc.tf             # VPC配置
│   │   ├── ecs.tf             # ECS配置
│   │   ├── efs.tf             # EFS配置（模型缓存）
│   │   ├── database.tf        # RDS Serverless v2配置
│   │   ├── mq.tf              # Amazon MQ for RabbitMQ配置
│   │   ├── s3.tf              # S3配置
│   │   ├── sns.tf             # SNS配置（S3事件通知）
│   │   ├── alb.tf             # ALB配置
│   │   └── ecs-services.tf    # ECS服务配置
│   └── scripts/                # 部署脚本
│       └── build-and-push.sh  # 构建和推送镜像脚本
├── aliyun/                    # 阿里云部署配置
│   └── ack/                   # ACK容器服务配置
│       ├── terraform/         # Terraform基础设施配置
│       │   ├── database.tf    # RDS Serverless配置
│       │   └── rabbitmq.tf   # 云消息队列RabbitMQ版Serverless配置
│       ├── kubernetes/        # Kubernetes配置
│       ├── nginx/             # Nginx配置（如需要）
│       └── scripts/           # 部署脚本
├── config/                    # 环境配置模板
│   ├── aws/                   # AWS环境变量模板
│   └── aliyun/                # 阿里云环境变量模板
├── local-dev/                 # 本地开发环境
└── docker-compose.prod.yml    # 生产环境Docker Compose配置
```

## 快速开始

### 1. 构建Docker镜像

#### AWS
```bash
cd deploy/aws/scripts
export AWS_ACCOUNT_ID=your-account-id
export AWS_REGION=us-east-1
export ENVIRONMENT=dev  # dev/test/prod
./build-and-push.sh
```

#### 阿里云
```bash
cd deploy/aliyun/ack/scripts
export REGISTRY=registry.cn-hangzhou.aliyuncs.com
export NAMESPACE=knowhere
export ALIYUN_USERNAME=your-username
export ALIYUN_PASSWORD=your-password
export ENVIRONMENT=dev  # dev/test/prod
./build-and-push.sh
```

### 2. 部署基础设施

#### AWS
```bash
cd deploy/aws/terraform
terraform init
# 版本号会自动从Git Tag获取，或手动指定
terraform plan \
  -var="environment=dev" \
  -var="domain_name=knowhere.ai" \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'dev')" \
  -var="db_password=your-db-password" \
  -var="mq_password=your-mq-password"
terraform apply
```

#### 阿里云
```bash
cd deploy/aliyun/ack/terraform
terraform init
# 版本号会自动从Git Tag获取，或手动指定
terraform plan \
  -var="environment=dev" \
  -var="domain_name=knowhere.ai" \
  -var="db_password=your-db-password" \
  -var="rabbitmq_password=your-rabbitmq-password"
terraform apply
```

### 3. 初始化Secrets Manager

#### AWS Secrets Manager

所有敏感信息（数据库密码、API密钥等）都存储在AWS Secrets Manager中，由Terraform统一管理。

**首次部署前验证**：
```bash
cd deploy/aws/scripts
export ENVIRONMENT=dev  # dev/test/prod
export AWS_REGION=us-east-1
./init-secrets.sh
```

此脚本会：
- 检查所有必需的secrets是否存在
- 验证IAM权限是否正确配置
- 提示缺失或空的secrets

**创建Secrets**：
Terraform会自动创建所有必需的secrets。如果某些secrets的值需要手动设置，使用以下命令：

```bash
# 设置S3访问密钥
aws secretsmanager update-secret \
  --secret-id "knowhere/dev/s3-access-key" \
  --secret-string "your-access-key-id" \
  --region us-east-1

# 设置应用密钥
aws secretsmanager update-secret \
  --secret-id "knowhere/dev/secret-key" \
  --secret-string "your-jwt-secret-key" \
  --region us-east-1

# 设置Stripe密钥
aws secretsmanager update-secret \
  --secret-id "knowhere/dev/stripe-secret-key" \
  --secret-string "sk_live_..." \
  --region us-east-1
```

**必需的Secrets列表**：
- `knowhere/{environment}/database-url` - 数据库连接URL（自动生成）
- `knowhere/{environment}/redis-host` - Redis主机（自动生成）
- `knowhere/{environment}/redis-port` - Redis端口（自动生成）
- `knowhere/{environment}/redis-password` - Redis密码（默认空）
- `knowhere/{environment}/rabbitmq-host` - RabbitMQ主机（自动生成）
- `knowhere/{environment}/rabbitmq-username` - RabbitMQ用户名（自动生成）
- `knowhere/{environment}/rabbitmq-password` - RabbitMQ密码（从变量设置）
- `knowhere/{environment}/s3-access-key` - S3访问密钥ID（需手动设置）
- `knowhere/{environment}/s3-secret-key` - S3秘密访问密钥（需手动设置）
- `knowhere/{environment}/secret-key` - 应用JWT密钥（需手动设置）
- `knowhere/{environment}/stripe-secret-key` - Stripe密钥（可选）
- `knowhere/{environment}/stripe-publishable-key` - Stripe发布密钥（可选）
- `knowhere/{environment}/posthog-key` - PostHog密钥（可选）

**IAM权限**：
Terraform会自动配置ECS任务执行角色的Secrets Manager访问权限。确保运行`terraform apply`以应用IAM策略。

#### 阿里云Kubernetes Secrets

阿里云使用Kubernetes Secrets存储敏感信息。

**创建Secrets**：
```bash
# 方式1：使用kubectl命令（推荐）
kubectl create secret generic knowhere-secrets \
  --from-literal=database-url='postgresql+asyncpg://user:password@host:5432/knowhere' \
  --from-literal=redis-host='redis-endpoint' \
  --from-literal=redis-port='6379' \
  --from-literal=redis-password='' \
  --from-literal=rabbitmq-host='rabbitmq-endpoint' \
  --from-literal=rabbitmq-username='admin' \
  --from-literal=rabbitmq-password='password' \
  --from-literal=oss-access-key-id='your-access-key-id' \
  --from-literal=oss-secret-access-key='your-secret-access-key' \
  --from-literal=secret-key='your-secret-key' \
  --namespace=knowhere

# 方式2：使用YAML文件（参考 deploy/aliyun/ack/kubernetes/base/secrets.yaml）
# 注意：需要先base64编码所有值
echo -n 'your-value' | base64
# 然后替换secrets.yaml中的占位符
kubectl apply -f deploy/aliyun/ack/kubernetes/base/secrets.yaml
```

**安全建议**：
- 生产环境建议使用阿里云Secrets Manager配合KMS加密
- 不要将包含实际值的secrets.yaml提交到版本控制
- 定期轮换密钥

### 4. 配置S3/OSS事件通知

#### AWS S3 + SNS
Terraform会自动配置S3事件通知到SNS Topic，并订阅到API webhook endpoint。

#### 阿里云 OSS
运行配置脚本：
```bash
cd deploy/aliyun/ack/scripts
export OSS_BUCKET_NAME=your-bucket-name
export API_WEBHOOK_ENDPOINT=https://dev-api.knowhere.ai/v1/internal/s3-events
./setup-oss-events.sh
```

## 环境配置

### 多环境支持

项目支持三个环境：
- `dev` - 开发环境
- `test` - 测试环境
- `prod` - 生产环境

每个环境使用独立的：
- 域名（dev-api.knowhere.ai, test-api.knowhere.ai, api.knowhere.ai）
- 存储桶（knowhere-dev-storage-xxx, knowhere-test-storage-xxx, knowhere-prod-storage-xxx）
- SNS Topic / OSS事件配置
- EFS / NAS文件系统（模型缓存）
- ECS集群 / ACK集群
- 配置和密钥

### 环境变量配置

复制环境变量模板并填入实际值：

```bash
# AWS
cp deploy/config/aws/env.template deploy/config/aws/.env.dev
# 编辑 .env.dev 填入实际值

# 阿里云
cp deploy/config/aliyun/env.template deploy/config/aliyun/.env.dev
# 编辑 .env.dev 填入实际值
```

## Serverless基础设施

### AWS平台

- **RDS Serverless v2**: Aurora PostgreSQL Serverless v2，自动扩缩容（0.5-16 ACU）
- **ElastiCache Serverless**: Redis Serverless，按使用量计费
- **Amazon MQ for RabbitMQ**: 完全托管的RabbitMQ服务（非严格Serverless，但无需管理服务器）
- **S3**: 对象存储（已Serverless）

### 阿里云平台

- **RDS Serverless**: PostgreSQL Serverless，自动启停和扩缩容
- **Redis Serverless**: Redis云数据库Serverless版，自动扩缩容
- **云消息队列RabbitMQ版Serverless**: Serverless实例，按量计费，自动弹性扩展
- **OSS**: 对象存储（已Serverless）

## 版本管理

### Git Tag版本管理

项目使用语义化版本（semver）进行版本管理：

1. **创建版本Tag**:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

2. **版本号获取规则**:
   - 如果有精确匹配的Git Tag，使用Tag（如 `v1.0.0`）
   - 如果有Tag但不是精确匹配，使用Tag+commit hash（如 `v1.0.0-abc1234`）
   - 如果没有Tag，使用commit hash（如 `dev-abc1234`）

3. **版本信息注入**:
   - 构建时自动从Git Tag获取版本号
   - 版本号注入到Docker镜像环境变量（`APP_VERSION`）
   - 版本号包含在镜像标签中
   - API端点 `/v1/version` 返回当前部署版本信息

### 版本端点

- **GET /v1/version**: 返回版本信息
  ```json
  {
    "version": "v1.0.0",
    "commit": "abc1234",
    "build_time": "2024-01-01T00:00:00Z",
    "environment": "production",
    "service": "knowhere-api"
  }
  ```

- **GET /health**: 健康检查端点，包含版本信息

## RabbitMQ配置

### AWS平台（Amazon MQ）

- **端口**: 5671 (AMQPS over TLS)
- **管理端口**: 15671
- **连接信息**: 存储在AWS Secrets Manager
- **环境变量**: `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_PORT`, `RABBITMQ_VHOST`

### 阿里云平台（云消息队列RabbitMQ版Serverless）

- **端口**: 5672 (AMQP)
- **管理端口**: 15672
- **连接信息**: 存储在Kubernetes Secrets
- **环境变量**: `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_PORT`, `RABBITMQ_VHOST`

### 本地开发

本地开发环境继续使用Docker Compose中的RabbitMQ服务，无需修改代码。

## 镜像优化

### 多阶段构建

所有Dockerfile使用多阶段构建来减少镜像体积：

- **API镜像**: ~300-400MB（从~500MB优化）
- **Worker镜像**: ~1.5-2GB（从~3GB优化）
- **Web镜像**: 已优化（使用standalone模式）

### 模型缓存

Worker服务使用共享存储（AWS EFS / 阿里云NAS）来缓存模型，避免重复下载：

- 挂载点: `/mnt/models/huggingface`
- 环境变量: `HF_HOME`, `TRANSFORMERS_CACHE`

## 域名配置

### AWS
- 开发环境: `dev-api.knowhere.ai`, `dev.knowhere.ai`
- 测试环境: `test-api.knowhere.ai`, `test.knowhere.ai`
- 生产环境: `api.knowhere.ai`, `knowhere.ai`

### 阿里云
- 开发环境: `dev-api.knowhere.ai`, `dev.knowhere.ai`
- 测试环境: `test-api.knowhere.ai`, `test.knowhere.ai`
- 生产环境: `api.knowhere.ai`, `knowhere.ai`

## 监控和日志

### AWS
- CloudWatch日志组: `/ecs/knowhere-{environment}-{service}`
- CloudWatch Container Insights: 已启用
- 日志保留: dev/test 7天, prod 30天

### 阿里云
- 日志服务SLS: 自动配置
- 云监控: 已启用
- ACK监控面板: 已启用

## 安全最佳实践

### Secrets Manager安全

1. **加密存储**：
   - AWS: 所有secrets使用KMS加密存储
   - 阿里云: 使用Kubernetes Secrets + KMS（生产环境推荐）

2. **访问控制**：
   - AWS: IAM策略仅授予ECS任务执行角色必要的访问权限
   - 阿里云: 使用RBAC控制Secret访问权限

3. **密钥轮换**：
   - 定期轮换数据库密码、API密钥等敏感信息
   - AWS Secrets Manager支持自动轮换（需配置Lambda函数）
   - 轮换后无需重新部署，ECS会自动获取新值

4. **审计和监控**：
   - AWS: CloudTrail记录所有Secrets Manager访问
   - 定期审查访问日志，发现异常访问

5. **最小权限原则**：
   - 仅授予应用所需的最小权限
   - 不同环境使用不同的secrets

### 部署安全检查清单

- [ ] 所有secrets已创建并设置了正确的值
- [ ] IAM权限已正确配置
- [ ] Terraform state文件安全存储（S3 + DynamoDB锁）
- [ ] 生产环境启用了删除保护
- [ ] 密钥已从版本控制中排除
- [ ] 定期备份和恢复测试

## 故障排查

### 镜像构建失败
- 检查Dockerfile路径是否正确
- 确认构建上下文包含所有必要文件
- 检查.dockerignore配置

### 部署失败
- 检查环境变量是否正确设置
- 确认Terraform变量配置正确
- 查看CloudWatch/日志服务日志
- **检查Secrets Manager权限**：运行`./deploy/aws/scripts/init-secrets.sh`验证

### Secrets Manager访问失败
- 检查IAM角色是否有Secrets Manager访问权限
- 验证secret是否存在：`aws secretsmanager describe-secret --secret-id knowhere/dev/database-url`
- 检查KMS权限：确保ECS任务执行角色有KMS解密权限
- 查看ECS任务日志中的错误信息

### 模型加载失败
- 检查EFS/NAS挂载是否正确
- 确认Worker服务有正确的权限
- 查看Worker日志

## 更多信息

- [AWS部署详细文档](aws/README.md)
- [阿里云ACK部署详细文档](aliyun/ack/README.md)
- [本地开发环境](local-dev/README.md)

