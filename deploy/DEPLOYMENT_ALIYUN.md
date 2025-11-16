# 阿里云部署指南

本文档提供在阿里云平台部署 Knowhere 项目的完整指南。

## 📋 目录

- [架构概述](#架构概述)
- [前置要求](#前置要求)
- [部署流程](#部署流程)
- [镜像构建（ACR 构建服务）](#镜像构建acr构建服务)
- [基础设施部署](#基础设施部署)
- [应用部署](#应用部署)
- [环境配置](#环境配置)
- [监控和日志](#监控和日志)
- [故障排查](#故障排查)

## 架构概述

### 架构图

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
    │   RDS Serverless        │
    │   Redis Serverless      │
    │   OSS Storage           │
    │   RabbitMQ Serverless   │
    └─────────────────────────┘
```

### 核心组件

- **计算**: ACK (Alibaba Container Service for Kubernetes)
- **数据库**: RDS Serverless (PostgreSQL)
- **缓存**: Redis Serverless
- **消息队列**: 云消息队列 RabbitMQ 版 Serverless
- **存储**: OSS (对象存储)
- **负载均衡**: SLB (Server Load Balancer)
- **DNS**: 阿里云 DNS
- **密钥管理**: Kubernetes Secrets
- **镜像构建**: GitHub Actions + GitHub Container Registry (ghcr.io)

## 前置要求

### 1. 阿里云账户和权限

- 阿里云账户
- 具有以下权限的 RAM 用户或角色：
  - ACK 管理权限
  - RDS 管理权限
  - Redis 管理权限
  - OSS 管理权限
  - RabbitMQ 管理权限
  - SLB 管理权限
  - DNS 管理权限
  - Terraform 相关权限

### 2. 本地工具

- 阿里云 CLI
- Terraform >= 1.0
- kubectl
- Git

### 3. 域名

- 一个已注册的域名
- 域名在阿里云 DNS 中托管

### 4. GitHub 仓库

- 代码已推送到 GitHub 仓库
- 仓库已启用 GitHub Actions

## 部署流程

### 完整部署流程

```mermaid
graph TD
    A[准备环境] --> B[配置 Terraform]
    B --> C[初始化 Terraform Backend]
    C --> D[部署基础设施]
    D --> E[推送代码触发 GitHub Actions 构建]
    E --> F[镜像推送到 ghcr.io]
    F --> G[配置 Kubernetes Secrets]
    G --> H[部署 Kubernetes 资源]
    H --> I[配置 DNS]
    I --> J[配置 OSS 事件通知]
    J --> K[验证部署]
```

### 快速开始

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd knowhere

# 2. 配置阿里云凭证
aliyun configure

# 3. 进入部署目录
cd deploy/aliyun/ack/terraform

# 4. 按照后续步骤完成部署
```

## 镜像构建（GitHub Actions）

### 构建方式

**重要**: 项目使用 **GitHub Actions** 进行自动化构建，代码推送到 GitHub 仓库后会自动触发构建，构建完成后镜像自动推送到 GitHub Container Registry (ghcr.io)。

### GitHub Actions 构建优势

- ✅ **零维护成本**: 无需维护构建机器或 Runner
- ✅ **全球访问**: GitHub Actions 运行在海外，访问 Docker Hub 等资源速度快
- ✅ **自动触发**: 代码推送自动触发构建
- ✅ **免费额度**: 公开仓库完全免费，私有仓库有充足的免费额度
- ✅ **与 GitHub 深度集成**: 与代码仓库无缝集成

### 构建触发条件

GitHub Actions 会在以下情况自动触发构建：

- **分支推送**: 推送到 `main`、`dev`、`test` 分支
- **Tag 推送**: 推送以 `v` 开头的 tag（如 `v1.0.0`）
- **手动触发**: 在 GitHub Actions 页面手动触发，可选择环境和服务

### 环境判断逻辑

- `main` 分支 → `prod` 环境
- `test` 分支 → `test` 环境
- `dev` 分支 → `dev` 环境
- Tag 推送（v*） → `prod` 环境

### 镜像标签策略

每个构建会生成以下标签：

- `${ENVIRONMENT}-latest` - 环境最新版本（如 `dev-latest`, `test-latest`, `prod-latest`）
- `${VERSION}` - 版本号（tag 或 commit hash，如 `v1.0.0` 或 `dev-a1b2c3d`）
- `${ENVIRONMENT}-${COMMIT_SHORT}` - 环境+提交hash（如 `dev-a1b2c3d`）

### 镜像地址格式

镜像推送到 GitHub Container Registry，地址格式为：

```
ghcr.io/<github-username>/knowhere-{service}:{tag}
```

例如：
- `ghcr.io/your-username/knowhere-backend:dev-latest`
- `ghcr.io/your-username/knowhere-frontend:prod-latest`
- `ghcr.io/your-username/knowhere-worker:test-latest`

### 查看构建状态

1. **GitHub Actions 页面**
   - 访问：`https://github.com/<username>/<repo>/actions`
   - 查看构建历史和日志

2. **构建日志**
   - 点击具体的 workflow run
   - 查看每个服务的构建日志

### 详细配置文档

完整的 GitHub Actions 构建配置请参考：[GitHub Actions 构建指南](GITHUB_ACTIONS_BUILD.md)

## 基础设施部署

### Terraform 配置

#### 1. 初始化配置文件

```bash
cd deploy/aliyun/ack/terraform

# 复制配置模板
cp terraform.tfvars.example terraform.tfvars.dev
cp backend-config.dev.example backend-config.dev

# 编辑配置文件，填入实际值
vim terraform.tfvars.dev
```

#### 2. 配置变量

编辑 `terraform.tfvars.dev`，设置以下变量：

```hcl
region = "cn-guangzhou"
project_name = "knowhere"
environment = "dev"
domain_name = "knowhereto.com"
access_key = "your-access-key"
secret_key = "your-secret-key"
db_password = "your-secure-password"
rabbitmq_password = "your-rabbitmq-password"
```

详细变量说明请参考：[阿里云 Terraform 配置指南](aliyun/ack/terraform/README.md)

#### 3. 初始化 Backend

首次部署前，需要创建 Backend 资源（OSS）：

```bash
cd deploy/aliyun/ack/terraform/scripts
./init-backend.sh dev
```

脚本会自动创建：
- OSS Bucket: `knowhere-terraform-state-dev`

#### 4. 初始化 Terraform

```bash
cd deploy/aliyun/ack/terraform
terraform init -backend-config=backend-config.dev
```

#### 5. 规划部署

```bash
terraform plan \
  -var-file=terraform.tfvars.dev \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'dev-$(git rev-parse --short HEAD)')"
```

#### 6. 应用配置

```bash
terraform apply \
  -var-file=terraform.tfvars.dev \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'dev-$(git rev-parse --short HEAD)')"
```

### 创建的资源

Terraform 会自动创建以下资源：

- **网络**:
  - VPC 和交换机
  - 安全组
  - NAT Gateway

- **计算**:
  - ACK 集群
  - 节点池

- **数据库**:
  - RDS Serverless (PostgreSQL)
  - Redis Serverless

- **消息队列**:
  - 云消息队列 RabbitMQ 版 Serverless

- **存储**:
  - OSS 存储桶
  - NAS 文件系统（模型缓存）

- **网络服务**:
  - SLB (负载均衡)
  - DNS 记录

- **监控**:
  - 日志服务 SLS
  - 云监控

## 应用部署

### 1. 配置 kubeconfig

```bash
cd deploy/aliyun/ack/terraform

# 设置环境变量
export ALICLOUD_ACCESS_KEY=$(grep "^access_key" terraform.tfvars.dev | cut -d'"' -f2)
export ALICLOUD_SECRET_KEY=$(grep "^secret_key" terraform.tfvars.dev | cut -d'"' -f2)

# 获取 kubeconfig
terraform output -raw kubeconfig > ~/.kube/config-knowhere-dev

# 设置 KUBECONFIG 环境变量
export KUBECONFIG=~/.kube/config-knowhere-dev

# 验证连接
kubectl cluster-info
kubectl get nodes
```

### 2. 配置 Kubernetes Secrets

Kubernetes Secrets 需要从 Terraform 输出或配置文件中获取。

#### 方式一：使用 kubectl 命令（推荐）

```bash
# 获取 Terraform 输出值
cd deploy/aliyun/ack/terraform
terraform output

# 创建 Secrets
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
```

#### 方式二：使用 YAML 文件

参考 `deploy/aliyun/ack/kubernetes/base/secrets.yaml`，需要先 base64 编码所有值：

```bash
echo -n 'your-value' | base64
# 然后替换 secrets.yaml 中的占位符
kubectl apply -f deploy/aliyun/ack/kubernetes/base/secrets.yaml
```

### 3. 部署 Kubernetes 资源

#### 使用部署脚本（推荐）

```bash
cd deploy/aliyun/ack/scripts

# 设置环境变量
export ENVIRONMENT=dev
export API_DOMAIN=apidev.knowhereto.com
export WEB_DOMAIN=dev.knowhereto.com
export API_URL=https://apidev.knowhereto.com
export REGISTRY=ghcr.io
export NAMESPACE=your-github-username  # 替换为实际的 GitHub 用户名
export APP_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null || echo "dev-$(git rev-parse --short HEAD)")

# 获取 OSS bucket 名称
export OSS_BUCKET_NAME=$(cd ../terraform && terraform output -raw oss_bucket_name)

# 部署
./deploy-k8s.sh
```

脚本会自动：
- 根据环境设置正确的域名
- 替换 Kubernetes 配置文件中的环境变量占位符
- 应用所有资源到集群

#### 手动部署

```bash
cd deploy/aliyun/ack/kubernetes

# 使用 kustomize 部署
kubectl apply -k dev/

# 或直接应用 base 配置（需要先替换环境变量）
kubectl apply -f base/
```

### 4. 配置 DNS

将域名指向 SLB 公网 IP：

```bash
cd deploy/aliyun/ack/terraform

# 获取 SLB 地址
terraform output slb_address_for_dns
# 输出: 8.163.26.197

# 配置 DNS（使用脚本或手动配置）
cd ../scripts
./configure-dns.sh dev
```

需要配置的 DNS 记录：
- `apidev.knowhereto.com` → `8.163.26.197` (A 记录)
- `dev.knowhereto.com` → `8.163.26.197` (A 记录)

### 5. 配置 OSS 事件通知

运行配置脚本：

```bash
cd deploy/aliyun/ack/scripts
export OSS_BUCKET_NAME=knowhere-dev-storage-xxxxx
export API_WEBHOOK_ENDPOINT=https://apidev.knowhereto.com/v1/internal/oss-events
./setup-oss-events.sh
```

## 环境配置

### 多环境支持

项目支持三个环境：`dev`、`test`、`prod`

每个环境使用独立的：
- 配置文件（`terraform.tfvars.{environment}`）
- Terraform State（OSS Backend）
- 资源（ACK 集群、RDS、OSS 等）
- 域名和证书

### 环境差异

| 配置项 | dev | test | prod |
|--------|-----|------|------|
| ACK 集群工作节点数 | 2 | 2 | 3 |
| RDS 实例数 | 1 | 1 | 1 (高可用配置) |
| RabbitMQ max_tps | 1000 | 1000 | 5000 |
| RabbitMQ max_connections | 500 | 500 | 1000 |
| 日志保留 | 7 天 | 7 天 | 30 天 |
| 删除保护 | 关闭 | 关闭 | 开启 |

详细环境配置请参考：[阿里云 Terraform 配置指南](aliyun/ack/terraform/README.md)

## 监控和日志

### 日志服务 SLS

- 自动配置日志收集
- 支持日志查询和分析
- 支持日志告警

查看日志：

```bash
# 使用 kubectl 查看 Pod 日志
kubectl logs -n knowhere -l app=knowhere-api --tail=50

# 或通过阿里云控制台查看 SLS 日志
```

### 云监控

- 已启用云监控
- 支持资源监控和告警
- 支持自定义监控指标

### ACK 监控面板

- Kubernetes Dashboard
- 资源使用情况
- Pod 状态监控

### 健康检查

- **后端**: `https://apidev.knowhereto.com/health`
- **前端**: `https://dev.knowhereto.com/`
- **版本信息**: `https://apidev.knowhereto.com/v1/version`

## 故障排查

### 常见问题

#### 1. Pod 无法启动

**检查步骤**:
1. 查看 Pod 日志
   ```bash
   kubectl logs -n knowhere <pod-name>
   ```

2. 查看 Pod 事件
   ```bash
   kubectl describe pod -n knowhere <pod-name>
   ```

3. 检查镜像是否存在
   ```bash
   # 在 GitHub Container Registry 检查镜像
   # 访问：https://github.com/<username>/<repo>/pkgs/container/knowhere-backend
   # 或使用 docker pull 测试
   docker pull ghcr.io/<username>/knowhere-backend:dev-latest
   ```

4. 验证 Secrets 是否正确
   ```bash
   kubectl get secret knowhere-secrets -n knowhere -o yaml
   ```

#### 2. GitHub Actions 构建失败

**检查步骤**:
1. 在 GitHub Actions 页面查看构建日志
2. 检查 Dockerfile 路径是否正确
3. 检查 workflow 配置
4. 验证 GitHub 仓库权限和 Actions 是否启用

**常见错误**:
- `Dockerfile not found`: 检查 Dockerfile 路径
- `Build timeout`: 检查构建时间是否过长
- `Permission denied`: 检查 GitHub Actions 权限设置
- `Image push failed`: 检查 GitHub Container Registry 权限

详细故障排查请参考：[GitHub Actions 构建指南](GITHUB_ACTIONS_BUILD.md#故障排查)

#### 3. Ingress 无法访问

**检查步骤**:
1. 检查 Ingress 配置
   ```bash
   kubectl describe ingress -n knowhere knowhere-ingress
   ```

2. 检查 Ingress Controller
   ```bash
   kubectl get pods -n ingress-nginx
   ```

3. 检查 DNS 解析
   ```bash
   dig apidev.knowhereto.com
   ```

4. 检查 SLB 配置
   ```bash
   cd deploy/aliyun/ack/terraform
   terraform output slb_address
   ```

#### 4. 数据库连接失败

**检查步骤**:
1. 检查 RDS 安全组是否允许 ACK 节点访问
2. 验证数据库密码是否正确
3. 确认子网配置（ACK 和 RDS 在同一 VPC）
4. 检查 RDS 状态
   ```bash
   aliyun rds DescribeDBInstances --RegionId cn-guangzhou
   ```

#### 5. 镜像拉取失败

**检查步骤**:
1. 检查 GitHub Container Registry 权限
   - 如果仓库是私有的，需要配置 imagePullSecrets
   - 参考 [GitHub Actions 构建指南](GITHUB_ACTIONS_BUILD.md#配置-kubernetes-镜像拉取)

2. 验证镜像标签
   ```bash
   # 在 GitHub 上查看镜像标签
   # 访问：https://github.com/<username>/<repo>/pkgs/container/knowhere-backend
   ```

3. 检查 Kubernetes Secret（imagePullSecrets）
   ```bash
   kubectl get secret -n knowhere
   # 确保配置了 ghcr.io 的 imagePullSecrets
   ```

### 调试命令

```bash
# 查看 Pod 状态
kubectl get pods -n knowhere

# 查看 Service
kubectl get svc -n knowhere

# 查看 Ingress
kubectl get ingress -n knowhere

# 查看 Deployment
kubectl get deployment -n knowhere

# 查看事件
kubectl get events -n knowhere --sort-by='.lastTimestamp'

# 进入 Pod 调试
kubectl exec -it -n knowhere <pod-name> -- /bin/bash
```

## 相关文档

- [主部署指南](README.md)
- [阿里云 Terraform 配置指南](aliyun/ack/terraform/README.md)
- [GitHub Actions 构建指南](GITHUB_ACTIONS_BUILD.md)
- [Kubernetes 部署指南](aliyun/ack/kubernetes/README.md)
- [域名配置说明](DOMAIN_CONFIG.md)

---

**最后更新**: 2024-01-01  
**维护者**: DevOps Team

