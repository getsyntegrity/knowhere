# Knowhere 部署指南

本文档提供 Knowhere 项目在 AWS 和阿里云平台的完整部署指南。

## 📋 目录

- [架构概述](#架构概述)
- [快速开始](#快速开始)
- [平台选择](#平台选择)
- [部署方案](#部署方案)
- [环境配置](#环境配置)
- [版本管理](#版本管理)
- [监控和日志](#监控和日志)
- [故障排查](#故障排查)
- [相关文档](#相关文档)

## 架构概述

Knowhere 项目采用容器化部署架构，支持在 AWS 和阿里云两个云平台运行。

### 核心组件

- **Frontend**: Next.js 前端应用
- **Backend**: FastAPI 后端服务
- **Worker**: Celery 异步任务处理服务

### 基础设施

- **计算**: AWS ECS Fargate / 阿里云 ACK (Kubernetes)
- **数据库**: AWS RDS Serverless v2 / 阿里云 RDS Serverless (PostgreSQL)
- **缓存**: AWS ElastiCache Serverless / 阿里云 Redis Serverless
- **消息队列**: AWS Amazon MQ for RabbitMQ / 阿里云云消息队列 RabbitMQ 版 Serverless
- **存储**: AWS S3 / 阿里云 OSS
- **负载均衡**: AWS ALB / 阿里云 SLB
- **DNS**: AWS Route53 / 阿里云 DNS

## 快速开始

### 选择部署平台

根据你的需求选择部署平台：

- **AWS 部署**: 适合海外用户，使用 ECS Fargate，本地构建镜像推送到 ECR
- **阿里云部署**: 适合国内用户，使用 ACK (Kubernetes)，使用 ACR 构建服务自动构建镜像

### 快速部署

#### AWS 部署

```bash
# 1. 查看 AWS 部署指南
cat deploy/DEPLOYMENT_AWS.md

# 2. 进入 AWS 部署目录
cd deploy/aws/terraform

# 3. 按照 AWS 部署指南完成部署
```

详细步骤请参考：[AWS 部署指南](DEPLOYMENT_AWS.md)

#### 阿里云部署

```bash
# 1. 查看阿里云部署指南
cat deploy/DEPLOYMENT_ALIYUN.md

# 2. 进入阿里云部署目录
cd deploy/aliyun/ack/terraform

# 3. 按照阿里云部署指南完成部署
```

详细步骤请参考：[阿里云部署指南](DEPLOYMENT_ALIYUN.md)

## 平台选择

### AWS 平台

**适用场景**:
- 面向海外用户
- 需要 AWS 生态集成
- 使用 ECS Fargate 无服务器容器

**特点**:
- ✅ 本地构建镜像，推送到 ECR
- ✅ 使用 ECS Fargate，无需管理服务器
- ✅ 使用 AWS Secrets Manager 管理密钥
- ✅ 使用 CloudWatch 监控和日志

**文档**: [AWS 部署指南](DEPLOYMENT_AWS.md)

### 阿里云平台

**适用场景**:
- 面向国内用户
- 需要阿里云生态集成
- 使用 Kubernetes 容器编排

**特点**:
- ✅ 使用 ACR 构建服务，自动构建镜像（无需本地构建）
- ✅ 使用 ACK (Kubernetes)，支持更灵活的编排
- ✅ 使用 Kubernetes Secrets 管理密钥
- ✅ 使用阿里云日志服务 SLS 监控和日志

**文档**: [阿里云部署指南](DEPLOYMENT_ALIYUN.md)

## 部署方案

### 镜像构建方式对比

| 平台 | 构建方式 | 说明 |
|------|---------|------|
| AWS | 本地构建 + ECR | 使用 `build-and-push.sh` 脚本在本地构建并推送到 ECR |
| 阿里云 | ACR 构建服务 | 配置构建规则，代码推送自动触发构建，无需本地构建 |

### 部署架构对比

#### AWS 架构

```
Internet
    ↓
Route 53 (DNS)
    ↓
Application Load Balancer (ALB)
    ↓
┌─────────────────┬─────────────────┬─────────────────┐
│   Frontend      │   Backend       │   Worker        │
│   (Next.js)     │   (FastAPI)     │   (Celery)      │
│   ECS Fargate   │   ECS Fargate   │   ECS Fargate   │
└─────────────────┴─────────────────┴─────────────────┘
    ↓                     ↓                     ↓
    └─────────┬───────────┴─────────────────────┘
              ↓
    ┌─────────────────────────┐
    │   RDS + ElastiCache     │
    │   S3 + Amazon MQ        │
    └─────────────────────────┘
```

#### 阿里云架构

```
Internet
    ↓
阿里云 DNS
    ↓
SLB (负载均衡)
    ↓
ACK (Kubernetes)
    ↓
┌─────────────────┬─────────────────┬─────────────────┐
│   Frontend      │   Backend       │   Worker        │
│   (Next.js)     │   (FastAPI)     │   (Celery)      │
│   Kubernetes    │   Kubernetes    │   Kubernetes    │
│   Deployment    │   Deployment    │   Deployment    │
└─────────────────┴─────────────────┴─────────────────┘
    ↓                     ↓                     ↓
    └─────────┬───────────┴─────────────────────┘
              ↓
    ┌─────────────────────────┐
    │   RDS + Redis           │
    │   OSS + RabbitMQ        │
    └─────────────────────────┘
```

## 环境配置

### 多环境支持

项目支持三个环境：

- **dev**: 开发环境
- **test**: 测试环境
- **prod**: 生产环境

### 域名配置

| 服务 | 环境 | 域名 | Git分支 |
|------|------|------|---------|
| **API** | prod | `api.knowhereto.com` | main |
| **API** | test | `apitest.knowhereto.com` | test |
| **API** | dev | `apidev.knowhereto.com` | dev |
| **Web** | prod | `knowhereto.com` | main |
| **Web** | test | `test.knowhereto.com` | test |
| **Web** | dev | `dev.knowhereto.com` | dev |

详细域名配置请参考：[域名配置说明](DOMAIN_CONFIG.md)

### 环境变量配置

#### AWS 环境变量

配置文件位置：`deploy/config/aws/env.template`

```bash
# 复制模板
cp deploy/config/aws/env.template deploy/config/aws/.env.dev

# 编辑配置文件，填入实际值
```

#### 阿里云环境变量

配置文件位置：`deploy/config/aliyun/env.template`

```bash
# 复制模板
cp deploy/config/aliyun/env.template deploy/config/aliyun/.env.dev

# 编辑配置文件，填入实际值
```

## 版本管理

### Git Tag 版本管理

项目使用语义化版本（semver）进行版本管理：

1. **创建版本 Tag**:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

2. **版本号获取规则**:
   - 如果有精确匹配的 Git Tag，使用 Tag（如 `v1.0.0`）
   - 如果有 Tag 但不是精确匹配，使用 Tag+commit hash（如 `v1.0.0-abc1234`）
   - 如果没有 Tag，使用 commit hash（如 `dev-abc1234`）

3. **版本信息注入**:
   - 构建时自动从 Git Tag 获取版本号
   - 版本号注入到 Docker 镜像环境变量（`APP_VERSION`）
   - 版本号包含在镜像标签中
   - API 端点 `/v1/version` 返回当前部署版本信息

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

## 监控和日志

### AWS 监控

- **CloudWatch 日志组**: `/ecs/knowhere-{environment}-{service}`
- **CloudWatch Container Insights**: 已启用
- **日志保留**: dev/test 7天, prod 30天

### 阿里云监控

- **日志服务 SLS**: 自动配置
- **云监控**: 已启用
- **ACK 监控面板**: 已启用

## 故障排查

### 通用问题

#### 服务无法启动

1. 检查环境变量配置
2. 查看日志输出
3. 验证网络连接
4. 检查资源配额

#### 数据库连接失败

1. 检查数据库安全组配置
2. 验证数据库密码
3. 确认子网配置
4. 检查数据库状态

#### 镜像拉取失败

1. 检查镜像仓库权限
2. 验证镜像标签
3. 确认网络连接
4. 检查镜像是否存在

### 平台特定问题

#### AWS 特定问题

- **ECS 服务无法启动**: 参考 [AWS 部署指南](DEPLOYMENT_AWS.md#故障排查)
- **Secrets Manager 访问失败**: 检查 IAM 权限
- **ALB 健康检查失败**: 检查安全组和路由配置

#### 阿里云特定问题

- **Pod 无法启动**: 参考 [阿里云部署指南](DEPLOYMENT_ALIYUN.md#故障排查)
- **ACR 构建失败**: 检查构建规则配置和代码仓库权限
- **Ingress 无法访问**: 检查 Ingress Controller 和 DNS 配置

## 相关文档

### 主要文档

- [AWS 部署指南](DEPLOYMENT_AWS.md) - AWS 平台完整部署指南
- [阿里云部署指南](DEPLOYMENT_ALIYUN.md) - 阿里云平台完整部署指南
- [域名配置说明](DOMAIN_CONFIG.md) - 详细的域名配置说明
- [文档索引](DOCUMENTATION_INDEX.md) - 所有部署相关文档的索引

### 平台特定文档

#### AWS

- [AWS Terraform 配置指南](aws/terraform/README.md) - Terraform 多环境配置
- [AWS Worker 部署指南](aws/WORKER_DEPLOYMENT_GUIDE.md) - Worker 服务部署说明

#### 阿里云

- [阿里云 Terraform 配置指南](aliyun/ack/terraform/README.md) - Terraform 多环境配置
- [ACR 构建服务配置](aliyun/ack/ACR_BUILD_SERVICE_CONFIG.md) - ACR 自动构建配置
- [Kubernetes 部署指南](aliyun/ack/kubernetes/README.md) - Kubernetes 资源部署

### 本地开发

- [本地开发环境](local-dev/README.md) - 本地开发环境配置
- [Docker 快速开始](docker/QUICK_START.md) - Docker 容器快速开始

---

**最后更新**: 2024-01-01  
**维护者**: DevOps Team
