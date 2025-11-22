# GitHub Actions 构建指南

本文档提供使用 GitHub Actions 构建 Docker 镜像并推送到 GitHub Container Registry (ghcr.io) 的完整指南。

## 概述

项目使用 GitHub Actions 进行自动化构建，当代码推送到特定分支或 tag 时，会自动构建三个服务的 Docker 镜像并推送到 GitHub Container Registry。

## 构建服务

项目包含三个服务，每个服务都有独立的 Dockerfile：

- **API 服务** (`knowhere-backend`)
  - Dockerfile: `deploy/docker/Dockerfile.api`
  - 镜像名称: `knowhere-backend`

- **Web 服务** (`knowhere-frontend`)
  - Dockerfile: `deploy/docker/Dockerfile.web`
  - 镜像名称: `knowhere-frontend`

- **Worker 服务** (`knowhere-worker`)
  - Dockerfile: `deploy/docker/Dockerfile.worker`
  - 镜像名称: `knowhere-worker`

## 触发条件

### 自动触发

GitHub Actions 会在以下情况自动触发构建：

1. **分支推送**
   - 推送到 `main` 分支 → 构建 `prod` 环境镜像（用于 Serverless 部署）
   - 推送到 `staging` 分支 → 构建 `staging` 环境镜像（用于 test 环境 ECS/EC2 部署）
   - **注意**: `dev` 分支不再触发构建（dev 环境仅本地开发）

2. **Tag 推送**
   - 推送以 `v` 开头的 tag（如 `v1.0.0`）→ 构建 `prod` 环境镜像

3. **Pull Request**
   - 创建或更新 PR 到 `main`、`staging` 分支时，会构建镜像但不推送（仅用于验证）

### 手动触发

可以在 GitHub Actions 页面手动触发构建：

1. 访问：`https://github.com/<username>/<repo>/actions/workflows/build-images.yml`
2. 点击 "Run workflow"
3. 选择：
   - **Environment**: `staging` 或 `prod`
   - **Service**: 留空构建所有服务，或选择特定服务（`api`、`web`、`worker`）

## 环境判断逻辑

| Git 引用 | 环境 | 分支 | 部署方案 |
|---------|------|------|----------|
| `refs/heads/main` | `prod` | `main` | Serverless (ECS Fargate/ACK) |
| `refs/heads/staging` | `staging` | `staging` | ECS/EC2 + Docker Compose |
| `refs/tags/v*` | `prod` | `main` | Serverless (ECS Fargate/ACK) |
| 手动触发 | 用户选择 | 根据环境选择 | 根据环境选择 |

## 前端环境变量配置

### NEXT_PUBLIC_API_URL 构建时注入

前端 Docker 镜像在构建时会注入 `NEXT_PUBLIC_API_URL` 环境变量，该变量会被嵌入到客户端 JavaScript 代码中。

**重要**: 系统会为 GHCR 和 ACR 分别构建镜像，每个镜像使用对应仓库的 API URL。

**配置方式**:
- 通过 GitHub Secrets 配置（推荐）：
  - `STAGING_GHCR_API_URL`: Staging 环境推送到 GHCR 的 API URL
  - `STAGING_ACR_API_URL`: Staging 环境推送到 ACR 的 API URL
  - `PROD_GHCR_API_URL`: Production 环境推送到 GHCR 的 API URL
  - `PROD_ACR_API_URL`: Production 环境推送到 ACR 的 API URL
- 如果不配置，使用默认值：
  - Staging GHCR: `https://apitest.knowhereto.ai`
  - Staging ACR: `https://apitest.knowhereto.com`
  - Production GHCR: `https://api.knowhereto.ai`
  - Production ACR: `https://api.knowhereto.com`

**构建流程**:
1. 如果配置了 ACR，系统会构建两次：
   - 第一次：使用 GHCR API URL 构建并推送到 GHCR
   - 第二次：使用 ACR API URL 构建并推送到 ACR
2. 如果只配置了 GHCR，只构建一次并推送到 GHCR

**注意**: 
- 该配置仅影响前端（web）服务的构建
- 不同环境和不同仓库会构建不同的镜像，镜像中包含对应环境的 API URL
- GHCR 镜像默认使用 `.ai` 域名（AWS 环境），ACR 镜像默认使用 `.com` 域名（阿里云环境）

## 镜像标签策略

**重要变更**: 镜像标签策略已更新，不再使用 commit hash，改为使用 TAG+分支名称。

### 新标签策略

1. **有 TAG 的情况**:
   - 标签格式: `{tag}-{branch}`（如 `v1.0.0-main`、`v1.0.0-staging`）
   - 同时生成: `{branch}-latest`（如 `main-latest`、`staging-latest`）
   - 示例: 
     - `v1.0.0-main` 和 `main-latest`
     - `v1.0.0-staging` 和 `staging-latest`

2. **没有 TAG 的情况**:
   - 标签格式: `{branch}-latest`（如 `main-latest`、`staging-latest`）
   - 示例: `main-latest`、`staging-latest`

### 旧标签策略（已废弃）

- ~~`{environment}-latest`~~ → 改为 `{branch}-latest`
- ~~`{environment}-{commit-hash}`~~ → 改为 `{tag}-{branch}` 或 `{branch}-latest`

## 镜像地址格式

镜像推送到 GitHub Container Registry，地址格式为：

```
ghcr.io/<github-username>/knowhere-{service}:{tag}
```

### 示例

假设 GitHub 用户名为 `your-username`：

- API 服务生产环境（main 分支）: `ghcr.io/your-username/knowhere-backend:main-latest`
- Web 服务生产环境（带 TAG）: `ghcr.io/your-username/knowhere-frontend:v1.0.0-main`
- Worker 服务预发布环境（staging 分支）: `ghcr.io/your-username/knowhere-worker:staging-latest`
- 特定版本（staging）: `ghcr.io/your-username/knowhere-backend:v1.0.0-staging`

## 查看构建状态

### GitHub Actions 页面

1. 访问：`https://github.com/<username>/<repo>/actions`
2. 点击 "Build and Push Docker Images" workflow
3. 查看构建历史和状态

### 构建日志

1. 点击具体的 workflow run
2. 展开 "build-and-push" job
3. 查看每个服务的构建日志：
   - `build-and-push (api)`
   - `build-and-push (web)`
   - `build-and-push (worker)`

### 查看镜像

1. 访问 GitHub 仓库的 Packages 页面
2. 或直接访问：`https://github.com/<username>/<repo>/pkgs/container/knowhere-backend`
3. 查看所有标签和版本

## 配置 Kubernetes 镜像拉取

### 公开仓库

如果 GitHub 仓库是公开的，镜像也是公开的，可以直接拉取：

```yaml
image: ghcr.io/your-username/knowhere-backend:dev-latest
```

### 私有仓库

如果 GitHub 仓库是私有的，需要配置 `imagePullSecrets`：

#### 1. 创建 GitHub Personal Access Token

1. 访问：https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 设置权限：
   - `read:packages` - 读取包
   - `write:packages` - 写入包（如果需要）
4. 生成并保存 token

#### 2. 创建 Kubernetes Secret

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<personal-access-token> \
  --namespace=knowhere
```

#### 3. 在 Deployment 中使用

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: knowhere-api
spec:
  template:
    spec:
      imagePullSecrets:
      - name: ghcr-secret
      containers:
      - name: api
        image: ghcr.io/your-username/knowhere-backend:dev-latest
```

## 构建参数

每个构建会传递以下构建参数到 Dockerfile：

- `ENVIRONMENT`: 环境名称（`dev`、`test`、`prod`）
- `APP_VERSION`: 版本号（tag 或 commit hash）
- `BUILD_TIME`: ISO 8601 格式的构建时间
- `GIT_COMMIT`: 完整的 Git commit hash

这些参数会作为环境变量注入到容器中。

## 构建缓存

GitHub Actions 使用 Docker Buildx 的 GitHub Actions 缓存（GHA cache）来加速构建：

- **缓存类型**: `type=gha`
- **缓存模式**: `mode=max`（缓存所有层）
- **缓存键**: 自动基于 Dockerfile 和构建上下文

这可以显著减少重复构建的时间。

## 故障排查

### 1. 构建失败：Dockerfile not found

**原因**: Dockerfile 路径不正确或不存在

**解决**:
1. 检查 `.github/workflows/build-images.yml` 中的 `dockerfile` 路径
2. 确保 Dockerfile 存在于指定路径
3. 确保构建上下文（`context: .`）正确

### 2. 构建失败：Permission denied

**原因**: GitHub Actions 权限不足

**解决**:
1. 检查仓库设置 → Actions → General
2. 确保 "Workflow permissions" 设置为：
   - "Read and write permissions"
   - 勾选 "Allow GitHub Actions to create and approve pull requests"
3. 确保仓库已启用 GitHub Actions

### 3. 推送失败：Image push failed

**原因**: GitHub Container Registry 权限问题

**解决**:
1. 检查 `GITHUB_TOKEN` 是否有 `packages:write` 权限
2. 默认的 `GITHUB_TOKEN` 应该有足够权限
3. 如果是私有仓库，确保 token 有访问权限

### 4. 镜像拉取失败：unauthorized

**原因**: Kubernetes 无法拉取私有镜像

**解决**:
1. 参考 [配置 Kubernetes 镜像拉取](#配置-kubernetes-镜像拉取)
2. 确保创建了正确的 `imagePullSecrets`
3. 验证 Personal Access Token 有效

### 5. 构建超时

**原因**: 构建时间过长

**解决**:
1. 检查 Dockerfile 是否优化（使用多阶段构建、缓存等）
2. 检查依赖安装是否耗时过长
3. 考虑使用构建缓存加速

### 6. 环境判断错误

**原因**: 分支名称或 tag 格式不正确

**解决**:
1. 确保分支名称是 `main`、`staging`
2. Tag 必须以 `v` 开头（如 `v1.0.0`）
3. 检查 workflow 中的环境判断逻辑

## 部署策略

### 分支部署策略

项目支持两个平台的部署（AWS 和阿里云），不同分支有不同的部署策略：

| 分支 | 构建镜像 | AWS 部署 | 阿里云部署 |
|------|---------|---------|-----------|
| `dev` | ❌ 不构建 | ❌ 不部署 | ❌ 不部署 |
| `staging` | ✅ 构建（TAG+分支名称） | ✅ EC2 固定服务器 | ✅ ECS 固定服务器 |
| `main` | ✅ 构建（TAG+分支名称） | ✅ ECS Fargate (serverless) | ✅ ACK+Serverless |

### 部署详情

#### dev 分支
- **构建**: 不触发构建流程
- **部署**: 不进行任何部署

#### staging 分支
- **构建**: 
  - 触发条件: 推送到 `staging` 分支
  - 镜像标签: `{tag}-staging` 或 `staging-latest`
- **AWS 部署**:
  - 方式: 直接部署到固定 EC2 服务器（IP: 184.169.176.3）
  - 方法: 通过 SSH 连接，使用 Docker 运行容器
  - 脚本: `deploy/aws/scripts/deploy-to-ec2.sh`
- **阿里云部署**:
  - 方式: 直接部署到固定 ECS 服务器（IP: 8.134.142.218）
  - 方法: 通过 SSH 连接，使用 Docker 运行容器
  - 脚本: `deploy/aliyun/scripts/deploy-to-ecs.sh`

#### main 分支
- **构建**: 
  - 触发条件: 推送到 `main` 分支或推送 tag
  - 镜像标签: `{tag}-main` 或 `main-latest`
- **AWS 部署**:
  - 方式: ECS Fargate (serverless)
  - 方法: 使用 Terraform 管理基础设施，ECS 服务自动部署
  - Workflow: `.github/workflows/deploy-aws.yml` (deploy-main job)
- **阿里云部署**:
  - 方式: ACK (Kubernetes) + Serverless 基础设施
  - 方法: 使用 Kubernetes 部署脚本，连接到现有的 dev 基础设施（但使用 prod 配置）
  - Workflow: `.github/workflows/deploy-aliyun-ack.yml` (deploy-main job)
  - 脚本: `deploy/aliyun/ack/scripts/deploy-k8s.sh`

### 部署 Workflow

项目包含以下部署 workflow：

1. **`.github/workflows/build-images.yml`**
   - 负责构建和推送 Docker 镜像
   - 触发: `main`、`staging` 分支推送

2. **`.github/workflows/deploy-aws.yml`**
   - 负责 AWS 平台部署
   - `deploy-main`: main 分支的 Fargate 部署
   - `deploy-staging`: staging 分支的 EC2 固定服务器部署

3. **`.github/workflows/deploy-aliyun-ack.yml`**
   - 负责阿里云平台部署
   - `deploy-main`: main 分支的 ACK 部署
   - `deploy-staging`: staging 分支的 ECS 固定服务器部署

## 最佳实践

### 1. 使用语义化版本

推送 tag 时使用语义化版本：

```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### 2. 定期清理旧镜像

GitHub Container Registry 有存储限制，定期清理不需要的镜像：

1. 访问 Packages 页面
2. 删除旧版本镜像
3. 保留 `-latest` 标签和最近的几个版本

### 3. 监控构建时间

定期检查构建时间，优化 Dockerfile：

- 使用多阶段构建
- 合理使用缓存
- 减少不必要的依赖

### 4. 使用环境变量

在 Kubernetes 部署中使用环境变量引用镜像：

```yaml
env:
  - name: IMAGE_TAG
    value: "main-latest"  # 或 "v1.0.0-main"
```

这样可以方便地切换版本。

### 5. 分支命名规范

- **main**: 生产环境分支，使用 serverless 部署
- **staging**: 预发布环境分支，使用固定服务器部署
- **dev**: 开发分支，不进行构建和部署

## 相关文档

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [GitHub Container Registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Buildx 文档](https://docs.docker.com/build/buildx/)
- [Kubernetes 部署指南](aliyun/ack/kubernetes/README.md)

---

**最后更新**: 2025-11-18  
**维护者**: DevOps Team

