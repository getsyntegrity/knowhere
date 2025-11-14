# 容器化部署指南

本文档描述了Knowhere项目的完整容器化部署方案，支持AWS ECS Fargate和阿里云ACK（容器服务）。

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
│   │   ├── s3.tf              # S3配置
│   │   ├── sns.tf             # SNS配置（S3事件通知）
│   │   ├── alb.tf             # ALB配置
│   │   └── ecs-services.tf    # ECS服务配置
│   └── scripts/                # 部署脚本
│       └── build-and-push.sh  # 构建和推送镜像脚本
├── aliyun/                    # 阿里云部署配置
│   └── ack/                   # ACK容器服务配置
│       ├── terraform/         # Terraform基础设施配置
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
terraform plan -var="environment=dev" -var="domain_name=knowhere.ai"
terraform apply
```

#### 阿里云
```bash
cd deploy/aliyun/ack/terraform
terraform init
terraform plan -var="environment=dev" -var="domain_name=knowhere.ai"
terraform apply
```

### 3. 配置S3/OSS事件通知

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

## 故障排查

### 镜像构建失败
- 检查Dockerfile路径是否正确
- 确认构建上下文包含所有必要文件
- 检查.dockerignore配置

### 部署失败
- 检查环境变量是否正确设置
- 确认Terraform变量配置正确
- 查看CloudWatch/日志服务日志

### 模型加载失败
- 检查EFS/NAS挂载是否正确
- 确认Worker服务有正确的权限
- 查看Worker日志

## 更多信息

- [AWS部署详细文档](aws/README.md)
- [阿里云ACK部署详细文档](aliyun/ack/README.md)
- [本地开发环境](local-dev/README.md)

