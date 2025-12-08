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

### 环境部署方案

项目支持三个环境，每个环境采用不同的部署方案：

- **dev 环境**: 不进行远程部署，仅本地开发（使用 `local-dev` 目录的 Docker Compose 配置）
- **test 环境**（staging 分支）: 使用 Docker + ECS/EC2 方案
  - 阿里云：ECS 服务器 + Docker Compose（包含所有基础服务）
  - AWS：EC2 服务器 + Docker Compose（包含所有基础服务）
- **prod 环境**（main 分支）: 使用 Serverless 方案
  - AWS：ECS Fargate（无服务器容器）+ RDS Serverless + ElastiCache Serverless
  - 阿里云：ACK (Kubernetes) + RDS Serverless + Redis Serverless

### 基础设施

#### Test 环境（ECS/EC2）

- **计算**: AWS EC2 / 阿里云 ECS（固定服务器）
- **数据库**: Docker 容器（PostgreSQL）
- **缓存**: Docker 容器（Redis）
- **消息队列**: Docker 容器（RabbitMQ）
- **存储**: AWS S3 / 阿里云 OSS
- **负载均衡**: Nginx（容器内）
- **DNS**: AWS Route53 / 阿里云 DNS

#### Prod 环境（Serverless）

- **计算**: AWS ECS Fargate / 阿里云 ACK (Kubernetes)
- **数据库**: AWS RDS Serverless v2 / 阿里云 RDS Serverless (PostgreSQL)
- **缓存**: AWS ElastiCache Serverless / 阿里云 Redis Serverless
- **消息队列**: AWS Amazon MQ for RabbitMQ / 阿里云云消息队列 RabbitMQ 版 Serverless
- **存储**: AWS S3 / 阿里云 OSS
- **负载均衡**: AWS ALB / 阿里云 SLB
- **DNS**: AWS Route53 / 阿里云 DNS

## 快速开始

### 选择部署平台和环境

根据你的需求选择部署平台和环境：

#### 开发环境（dev）

- **不进行远程部署**，仅本地开发
- 使用 `deploy/local-dev` 目录的 Docker Compose 配置
- 详细说明请参考：[本地开发环境](local-dev/README.md)

#### 测试环境（test，staging 分支）

- **AWS**: EC2 服务器 + Docker Compose
  - 适合海外用户
  - 使用固定 EC2 服务器，所有服务通过 Docker Compose 管理
  - 详细说明请参考：[AWS 部署指南 - Test 环境](DEPLOYMENT_AWS.md#test环境部署)
- **阿里云**: ECS 服务器 + Docker Compose
  - 适合国内用户
  - 使用固定 ECS 服务器，所有服务通过 Docker Compose 管理
  - 详细说明请参考：[阿里云 ECS 部署文档](aliyun/README.md)

#### 生产环境（prod，main 分支）

- **AWS**: ECS Fargate Serverless
  - 适合海外用户
  - 使用 ECS Fargate 无服务器容器，所有基础设施 Serverless
  - 详细说明请参考：[AWS 部署指南 - Prod 环境](DEPLOYMENT_AWS.md#生产环境部署)
- **阿里云**: ACK (Kubernetes) Serverless
  - 适合国内用户
  - 使用 ACK Kubernetes 集群，所有基础设施 Serverless
  - 详细说明请参考：[阿里云部署指南 - Prod 环境](DEPLOYMENT_ALIYUN.md#生产环境部署)

## 平台选择

### AWS 平台

**适用场景**:
- 面向海外用户
- 需要 AWS 生态集成

**Test 环境特点**:
- ✅ 使用固定 EC2 服务器
- ✅ Docker Compose 管理所有服务（应用 + 基础服务）
- ✅ GitHub Actions 自动构建并推送镜像到 GHCR
- ✅ 使用 GitHub Container Registry (ghcr.io)

**Prod 环境特点**:
- ✅ 使用 ECS Fargate 无服务器容器
- ✅ 所有基础设施 Serverless（RDS、ElastiCache、Amazon MQ）
- ✅ 使用 AWS Secrets Manager 管理密钥
- ✅ 使用 CloudWatch 监控和日志

**文档**: [AWS 部署指南](DEPLOYMENT_AWS.md)

### 阿里云平台

**适用场景**:
- 面向国内用户
- 需要阿里云生态集成

**Test 环境特点**:
- ✅ 使用固定 ECS 服务器
- ✅ Docker Compose 管理所有服务（应用 + 基础服务）
- ✅ GitHub Actions 自动构建并推送镜像到 ACR 和 GHCR
- ✅ 使用阿里云容器镜像服务 (ACR)

**Prod 环境特点**:
- ✅ 使用 ACK (Kubernetes) 容器编排
- ✅ 所有基础设施 Serverless（RDS、Redis、RabbitMQ）
- ✅ 使用 Kubernetes Secrets 管理密钥
- ✅ 使用阿里云日志服务 SLS 监控和日志

**文档**: [阿里云部署指南](DEPLOYMENT_ALIYUN.md)

## 部署方案

### 镜像构建方式

所有环境均使用 **GitHub Actions** 自动构建镜像：

- **构建触发**: 代码推送到 `main` 或 `staging` 分支，或推送 Git Tag
- **镜像仓库**: 
  - GitHub Container Registry (ghcr.io) - 所有环境
  - 阿里云容器镜像服务 (ACR) - 阿里云环境
- **镜像标签**: 
  - `staging-latest` - test 环境
  - `main-latest` 或 `v*` - prod 环境

详细说明请参考：[GitHub Actions 构建指南](GITHUB_ACTIONS_BUILD.md)

### 部署架构对比

#### Test 环境架构（ECS/EC2 + Docker Compose）

**AWS EC2 架构**:
```
Internet
    ↓
Route 53 (DNS)
    ↓
EC2 服务器
    ↓
Nginx (容器)
    ↓
┌─────────────────┬─────────────────┬─────────────────┐
│   Frontend      │   Backend       │   Worker        │
│   (Next.js)     │   (FastAPI)     │   (Celery)      │
│   Docker        │   Docker        │   Docker        │
└─────────────────┴─────────────────┴─────────────────┘
    ↓                     ↓                     ↓
    └─────────┬───────────┴─────────────────────┘
              ↓
    ┌─────────────────────────┐
    │   PostgreSQL (Docker)  │
    │   Redis (Docker)        │
    │   RabbitMQ (Docker)     │
    └─────────────────────────┘
    ↓
    S3 (对象存储)
```

**阿里云 ECS 架构**:
```
Internet
    ↓
阿里云 DNS
    ↓
ECS 服务器
    ↓
Nginx (容器)
    ↓
┌─────────────────┬─────────────────┬─────────────────┐
│   Frontend      │   Backend       │   Worker        │
│   (Next.js)     │   (FastAPI)     │   (Celery)      │
│   Docker        │   Docker        │   Docker        │
└─────────────────┴─────────────────┴─────────────────┘
    ↓                     ↓                     ↓
    └─────────┬───────────┴─────────────────────┘
              ↓
    ┌─────────────────────────┐
    │   PostgreSQL (Docker)  │
    │   Redis (Docker)        │
    │   RabbitMQ (Docker)     │
    └─────────────────────────┘
    ↓
    OSS (对象存储)
```

#### Prod 环境架构（Serverless）

**AWS ECS Fargate 架构**:
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
    │   RDS Serverless v2     │
    │   ElastiCache Serverless│
    │   S3 + Amazon MQ        │
    └─────────────────────────┘
```

**阿里云 ACK 架构**:
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
    │   RDS Serverless       │
    │   Redis Serverless     │
    │   OSS + RabbitMQ       │
    └─────────────────────────┘
```

### 部署方案对比表

| 环境 | 平台 | 计算 | 数据库 | 缓存 | 消息队列 | 部署方式 |
|------|------|------|--------|------|----------|----------|
| **dev** | 本地 | Docker | Docker | Docker | Docker | 本地开发，不部署 |
| **test** | AWS | EC2 | Docker | Docker | Docker | Docker Compose |
| **test** | 阿里云 | ECS | Docker | Docker | Docker | Docker Compose |
| **prod** | AWS | ECS Fargate | RDS Serverless | ElastiCache Serverless | Amazon MQ | Terraform + ECS |
| **prod** | 阿里云 | ACK (K8s) | RDS Serverless | Redis Serverless | RabbitMQ Serverless | Terraform + K8s |

## 环境配置

### 多环境支持

项目支持三个环境，每个环境采用不同的部署策略：

- **dev**: 开发环境
  - **不进行远程部署**，仅本地开发
  - 使用 `deploy/local-dev` 目录的 Docker Compose 配置
  - 所有服务在本地 Docker 容器中运行

- **test**: 测试环境
  - **Git 分支**: `staging`
  - **部署方案**: Docker + ECS/EC2（固定服务器）
  - **AWS**: EC2 服务器 + Docker Compose
  - **阿里云**: ECS 服务器 + Docker Compose
  - 所有服务（应用 + 基础服务）通过 Docker Compose 管理

- **prod**: 生产环境
  - **Git 分支**: `main`
  - **部署方案**: Serverless（无服务器）
  - **AWS**: ECS Fargate + RDS Serverless + ElastiCache Serverless
  - **阿里云**: ACK (Kubernetes) + RDS Serverless + Redis Serverless

### 域名配置

| 服务 | 环境 | 域名 | Git分支 | 部署方案 |
|------|------|------|---------|----------|
| **API** | prod | `api.knowhereto.com` | main | Serverless |
| **API** | test | `apitest.knowhereto.com` | staging | ECS/EC2 + Docker Compose |
| **API** | dev | `apidev.knowhereto.com` | dev | 本地开发（不部署） |
| **Web** | prod | `knowhereto.com` | main | Serverless |
| **Web** | test | `test.knowhereto.com` | staging | ECS/EC2 + Docker Compose |
| **Web** | dev | `dev.knowhereto.com` | dev | 本地开发（不部署） |

详细域名配置请参考：[域名配置说明](DOMAIN_CONFIG.md)

### 环境变量配置

#### AWS 环境变量

配置文件位置：`deploy/config/aws/env.template`

```bash
# 复制模板
cp deploy/config/aws/env.template deploy/config/aws/.env.dev

# 编辑配置文件，填入实际值
```

**重要配置项**:
- `GOOGLE_CLIENT_ID`: Google OAuth客户端ID（可选，运行时配置）
- `GOOGLE_CLIENT_SECRET`: Google OAuth客户端密钥（可选，运行时配置）

**注意**: 
- 每个环境（dev/test/prod）需要使用不同的Google OAuth应用，确保在Google Cloud Console中为每个环境创建独立的OAuth 2.0客户端ID
- `GOOGLE_CLIENT_ID`是运行时配置（不带`NEXT_PUBLIC_`前缀），同一个镜像可以在不同环境中使用不同的配置
- **配置驱动**: 如果配置了`GOOGLE_CLIENT_ID`和`GOOGLE_CLIENT_SECRET`，则启用Google登录；未配置则不显示Google登录按钮

#### 阿里云环境变量

配置文件位置：`deploy/config/aliyun/env.template`

```bash
# 复制模板
cp deploy/config/aliyun/env.template deploy/config/aliyun/.env.dev

# 编辑配置文件，填入实际值
```

**重要配置项**:
- **默认不配置**Google OAuth相关变量
- 如需启用Google登录，只需配置`GOOGLE_CLIENT_ID`和`GOOGLE_CLIENT_SECRET`即可

### Google OAuth 登录配置

Google OAuth登录功能采用配置驱动方式：如果配置了`GOOGLE_CLIENT_ID`和`GOOGLE_CLIENT_SECRET`，则启用Google登录；未配置则不显示Google登录按钮。

#### AWS环境配置

1. **创建Google OAuth应用**:
   - 访问 [Google Cloud Console](https://console.cloud.google.com/)
   - 创建OAuth 2.0客户端ID
   - 为每个环境（dev/test/prod）创建独立的客户端ID
   - 配置授权重定向URI：`https://<your-domain>/auth/callback/google`

2. **配置环境变量**:
   - 在`deploy/config/aws/.env.<environment>`中配置：
     ```bash
     GOOGLE_CLIENT_ID=your-google-client-id
     GOOGLE_CLIENT_SECRET=your-google-client-secret
     ```

3. **配置Terraform变量**（用于部署）:
   - 在`deploy/aws/terraform/terraform.tfvars`中配置：
     ```hcl
     google_client_id = "your-google-client-id"
     google_client_secret = "your-google-client-secret"
     ```
   - Terraform会自动将配置存储到AWS Secrets Manager
   - **运行时注入**: `GOOGLE_CLIENT_ID`会在容器运行时从Secrets Manager注入，前端通过服务端组件读取并传递给客户端组件
   - **镜像复用**: 同一个镜像可以在不同环境中使用，只需在运行时设置不同的环境变量

#### 阿里云环境配置

- **默认不配置**Google OAuth相关变量，前端不会显示Google登录按钮
- **如需启用**: 只需配置`GOOGLE_CLIENT_ID`和`GOOGLE_CLIENT_SECRET`，系统会自动启用Google登录
- **配置驱动**: 有配置就启用，没配置就不显示，无需区分平台

#### 多环境配置说明

- **dev环境**: 使用本地`.env`文件配置，用于本地开发测试
- **test环境**: 如需启用Google OAuth，使用独立的Google OAuth应用，配置在对应环境的`.env`文件中
- **prod环境**: 如需启用Google OAuth，使用独立的Google OAuth应用，配置在对应环境的`.env`文件中

**安全建议**:
- 每个环境使用不同的Google OAuth应用，确保环境隔离
- Google OAuth密钥存储在AWS Secrets Manager中，不要硬编码
- 定期轮换OAuth密钥

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
- [本地开发环境](local-dev/README.md) - 本地开发环境配置

---

**最后更新**: 2025-11-20
**维护者**: DevOps Team
