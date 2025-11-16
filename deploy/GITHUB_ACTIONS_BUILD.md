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
   - 推送到 `main` 分支 → 构建 `prod` 环境镜像
   - 推送到 `test` 分支 → 构建 `test` 环境镜像
   - 推送到 `dev` 分支 → 构建 `dev` 环境镜像

2. **Tag 推送**
   - 推送以 `v` 开头的 tag（如 `v1.0.0`）→ 构建 `prod` 环境镜像

3. **Pull Request**
   - 创建或更新 PR 到 `main`、`dev`、`test` 分支时，会构建镜像但不推送（仅用于验证）

### 手动触发

可以在 GitHub Actions 页面手动触发构建：

1. 访问：`https://github.com/<username>/<repo>/actions/workflows/build-images.yml`
2. 点击 "Run workflow"
3. 选择：
   - **Environment**: `dev`、`test` 或 `prod`
   - **Service**: 留空构建所有服务，或选择特定服务（`api`、`web`、`worker`）

## 环境判断逻辑

| Git 引用 | 环境 |
|---------|------|
| `refs/heads/main` | `prod` |
| `refs/heads/test` | `test` |
| `refs/heads/dev` | `dev` |
| `refs/tags/v*` | `prod` |
| 手动触发 | 用户选择 |

## 镜像标签策略

每个构建会生成以下标签：

1. **环境最新版本**: `${ENVIRONMENT}-latest`
   - 示例: `dev-latest`, `test-latest`, `prod-latest`
   - 用途: 指向该环境的最新构建

2. **版本号**: `${VERSION}`
   - 如果有 tag: 使用 tag 名称（如 `v1.0.0`）
   - 如果没有 tag: 使用 `dev-${COMMIT_SHORT}`（如 `dev-a1b2c3d`）
   - 用途: 标识特定版本

3. **环境+提交**: `${ENVIRONMENT}-${COMMIT_SHORT}`
   - 示例: `dev-a1b2c3d`, `prod-a1b2c3d`
   - 用途: 精确标识特定环境的特定提交

## 镜像地址格式

镜像推送到 GitHub Container Registry，地址格式为：

```
ghcr.io/<github-username>/knowhere-{service}:{tag}
```

### 示例

假设 GitHub 用户名为 `your-username`：

- API 服务开发环境: `ghcr.io/your-username/knowhere-backend:dev-latest`
- Web 服务生产环境: `ghcr.io/your-username/knowhere-frontend:prod-latest`
- Worker 服务测试环境: `ghcr.io/your-username/knowhere-worker:test-latest`
- 特定版本: `ghcr.io/your-username/knowhere-backend:v1.0.0`

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
1. 确保分支名称是 `main`、`dev`、`test`
2. Tag 必须以 `v` 开头（如 `v1.0.0`）
3. 检查 workflow 中的环境判断逻辑

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
    value: "dev-latest"
```

这样可以方便地切换版本。

## 相关文档

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [GitHub Container Registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Buildx 文档](https://docs.docker.com/build/buildx/)
- [Kubernetes 部署指南](aliyun/ack/kubernetes/README.md)

---

**最后更新**: 2024-01-01  
**维护者**: DevOps Team

