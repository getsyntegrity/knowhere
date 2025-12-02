# GitHub Secrets 配置清单

本文档列出在 GitHub 仓库中需要配置的所有 Secrets，用于支持自动化构建和部署流程。

## 📋 目录

- [必需 Secrets](#必需-secrets)
- [可选 Secrets](#可选-secrets)
- [配置说明](#配置说明)
- [按平台分类](#按平台分类)
- [配置步骤](#配置步骤)

## 必需 Secrets

### 1. 构建相关（所有平台）

这些 Secret 用于构建 Docker 镜像并推送到镜像仓库。

| Secret 名称 | 说明 | 是否必需 | 使用场景 |
|-----------|------|---------|---------|
| `GITHUB_TOKEN` | GitHub 自动生成的 token | ✅ 自动提供 | 推送到 GitHub Container Registry (ghcr.io) |

**注意**: `GITHUB_TOKEN` 由 GitHub Actions 自动提供，无需手动配置。

---

## AWS 平台 Secrets

### 2. AWS 部署必需 Secrets

| Secret 名称 | 说明 | 是否必需 | 使用场景 |
|-----------|------|---------|---------|
| `AWS_ACCESS_KEY_ID` | AWS 访问密钥 ID | ✅ 必需 | AWS 服务认证（ECR、ECS、Terraform） |
| `AWS_SECRET_ACCESS_KEY` | AWS 访问密钥 Secret | ✅ 必需 | AWS 服务认证（ECR、ECS、Terraform） |

### 3. AWS Test 环境部署 Secrets（staging 分支）

**注意**: 这些 Secrets 仅用于 **test 环境**（staging 分支）的 EC2 + Docker Compose 部署。

| Secret 名称 | 说明 | 是否必需 | 使用场景 |
|-----------|------|---------|---------|
| `AWS_EC2_SSH_KEY` | EC2 服务器的 SSH 私钥 | ✅ 必需（staging） | 通过 SSH 部署到固定 EC2 服务器 |
| `AWS_EC2_HOST` | EC2 服务器 IP 地址或域名 | ✅ 必需（staging） | 连接到 EC2 服务器 |
| `AWS_EC2_USER` | EC2 服务器 SSH 用户名 | ✅ 必需（staging） | SSH 登录用户名（通常是 `ec2-user` 或 `ubuntu`） |

**注意**: 
- Prod 环境（main 分支）使用 ECS Fargate Serverless 方案，不需要这些 Secrets
- 这些 Secrets 仅用于 test 环境的 EC2 部署

---

## 阿里云平台 Secrets

### 4. 阿里云部署必需 Secrets

| Secret 名称 | 说明 | 是否必需 | 使用场景 |
|-----------|------|---------|---------|
| `ALIYUN_ACCESS_KEY_ID` | 阿里云 AccessKey ID | ✅ 必需 | 阿里云服务认证 |
| `ALIYUN_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret | ✅ 必需 | 阿里云服务认证 |
| `ALIYUN_ACK_KUBECONFIG` | ACK 集群的 kubeconfig 配置 | ✅ 必需（main 分支，prod 环境） | 连接到 Kubernetes 集群进行部署（仅用于 prod 环境的 ACK 部署） |

### 5. 阿里云 Test 环境部署 Secrets（staging 分支）

**注意**: 这些 Secrets 仅用于 **test 环境**（staging 分支）的 ECS + Docker Compose 部署。

| Secret 名称 | 说明 | 是否必需 | 使用场景 |
|-----------|------|---------|---------|
| `ALIYUN_ECS_SSH_KEY` | ECS 服务器的 SSH 私钥 | ✅ 必需（staging） | 通过 SSH 部署到固定 ECS 服务器 |
| `ALIYUN_ECS_HOST` | ECS 服务器 IP 地址或域名 | ✅ 必需（staging） | 连接到 ECS 服务器 |
| `ALIYUN_ECS_USER` | ECS 服务器 SSH 用户名 | ✅ 必需（staging） | SSH 登录用户名（通常是 `root` 或 `ecs-user`） |

**注意**: 
- Prod 环境（main 分支）使用 ACK (Kubernetes) Serverless 方案，使用 `ALIYUN_ACK_KUBECONFIG` 而不是这些 Secrets
- 这些 Secrets 仅用于 test 环境的 ECS 部署

---

## 可选 Secrets

### 6. 阿里云容器镜像服务（ACR）可选配置

如果使用阿里云 ACR 作为镜像仓库（而不是 GitHub Container Registry），需要配置以下 Secrets：

| Secret 名称 | 说明 | 是否必需 | 使用场景 |
|-----------|------|---------|---------|
| `ALIYUN_ACR_REGISTRY` | ACR 镜像仓库地址 | ⚠️ 可选 | 如果配置，镜像会同时推送到 ACR |
| `ALIYUN_ACR_NAMESPACE` | ACR 命名空间 | ⚠️ 可选 | ACR 镜像仓库命名空间 |
| `ALIYUN_ACR_USERNAME` | ACR 登录用户名 | ⚠️ 可选 | ACR 镜像仓库登录用户名 |
| `ALIYUN_ACR_PASSWORD` | ACR 登录密码 | ⚠️ 可选 | ACR 镜像仓库登录密码 |

**注意**: 
- 如果不配置这些 Secret，系统会使用 GitHub Container Registry (ghcr.io) 作为默认镜像仓库
- 如果配置了 ACR，镜像会同时推送到 GHCR 和 ACR

### 7. 前端 API URL 配置（可选）

用于在构建时注入 `NEXT_PUBLIC_API_URL` 环境变量到前端 Docker 镜像中。根据不同的镜像仓库（GHCR 和 ACR）使用不同的 API URL。

| Secret 名称 | 说明 | 是否必需 | 使用场景 | 默认值 |
|-----------|------|---------|---------|--------|
| `STAGING_GHCR_API_URL` | Staging 环境推送到 GHCR 的 API URL | ⚠️ 可选 | GHCR 镜像构建 | `https://apitest.knowhereto.ai` |
| `STAGING_ACR_API_URL` | Staging 环境推送到 ACR 的 API URL | ⚠️ 可选 | ACR 镜像构建 | `https://apitest.knowhereto.com` |
| `PROD_GHCR_API_URL` | Production 环境推送到 GHCR 的 API URL | ⚠️ 可选 | GHCR 镜像构建 | `https://api.knowhereto.ai` |
| `PROD_ACR_API_URL` | Production 环境推送到 ACR 的 API URL | ⚠️ 可选 | ACR 镜像构建 | `https://api.knowhereto.com` |

**注意**:
- 这些 Secret 仅用于前端（web）服务的 Docker 镜像构建
- 如果不配置，构建时会使用默认值：
  - GHCR 镜像：使用 `.ai` 域名（AWS 环境）
  - ACR 镜像：使用 `.com` 域名（阿里云环境）
- 系统会为 GHCR 和 ACR 分别构建镜像，每个镜像使用对应的 API URL
- 示例配置：
  - `STAGING_GHCR_API_URL`: `https://apitest.knowhereto.ai`
  - `STAGING_ACR_API_URL`: `https://apitest.knowhereto.com`
  - `PROD_GHCR_API_URL`: `https://api.knowhereto.ai`
  - `PROD_ACR_API_URL`: `https://api.knowhereto.com`

### 8. 前端URL配置（可选）

用于API服务的运行时环境变量配置，用于Stripe Checkout成功/取消回调。

| Secret 名称 | 说明 | 是否必需 | 使用场景 | 默认值 |
|-----------|------|---------|---------|--------|
| `STAGING_FRONTEND_URL` | Staging环境前端URL | ⚠️ 可选 | API服务运行时配置 | `https://test.knowhereto.ai` (AWS) 或 `https://test.knowhereto.com` (阿里云) |
| `PROD_FRONTEND_URL` | Production环境前端URL | ⚠️ 可选 | API服务运行时配置 | `https://knowhereto.ai` (AWS) 或 `https://knowhereto.com` (阿里云) |

**注意**:
- 这些Secret用于API服务的运行时环境变量配置（不是构建时）
- 如果不配置，系统会根据部署平台使用默认值
- AWS环境默认使用`.ai`域名，阿里云环境默认使用`.com`域名
- 配置方式：GitHub仓库 → Settings → Secrets and variables → Actions → New repository secret
- 示例配置：
  - `STAGING_FRONTEND_URL`: `https://test.knowhereto.ai` (AWS) 或 `https://test.knowhereto.com` (阿里云)
  - `PROD_FRONTEND_URL`: `https://knowhereto.ai` (AWS) 或 `https://knowhereto.com` (阿里云)

### 9. Google OAuth 配置（可选）

**重要变更**: Google OAuth配置已改为**运行时配置**，不再在构建时注入。这样同一个镜像可以在不同环境中使用不同的配置。

| Secret 名称 | 说明 | 是否必需 | 使用场景 | 默认值 |
|-----------|------|---------|---------|--------|
| ~~`GOOGLE_CLIENT_ID_TEST`~~ | ~~已废弃~~ | ❌ 不再需要 | ~~不再使用~~ | - |
| ~~`GOOGLE_CLIENT_ID_PROD`~~ | ~~已废弃~~ | ❌ 不再需要 | ~~不再使用~~ | - |

**重要说明**:
- **运行时配置**: `GOOGLE_CLIENT_ID`现在通过运行时环境变量配置（不带`NEXT_PUBLIC_`前缀）
- **镜像复用**: 同一个镜像可以在不同环境中使用，只需在运行时设置不同的环境变量
- **配置驱动**: 如果配置了`GOOGLE_CLIENT_ID`和`GOOGLE_CLIENT_SECRET`，则启用Google登录；未配置则不显示Google登录按钮
- **无需区分平台**: 不再需要区分AWS或阿里云环境，只需检查是否配置了OAuth凭证即可
- **配置方式**:
  - **AWS环境**: 通过Terraform配置，`GOOGLE_CLIENT_ID`存储在AWS Secrets Manager中，运行时注入到容器
  - **阿里云环境**: 默认不配置，如需启用只需配置`GOOGLE_CLIENT_ID`和`GOOGLE_CLIENT_SECRET`即可
- **配置步骤**:
  1. 在Google Cloud Console中创建OAuth 2.0客户端ID
  2. 为每个环境（test/prod）创建独立的客户端ID
  3. 在AWS环境中，通过Terraform配置`google_client_id`变量，系统会自动存储到Secrets Manager
  4. 后端`GOOGLE_CLIENT_SECRET`同样通过Terraform配置到AWS Secrets Manager

---

## 配置说明

### Secret 值格式要求

1. **SSH 私钥** (`*_SSH_KEY`):
   - 必须是完整的 SSH 私钥内容（包括 `-----BEGIN ... PRIVATE KEY-----` 和 `-----END ... PRIVATE KEY-----`）
   - 支持 RSA、ECDSA、Ed25519 格式
   - 建议使用 Ed25519 格式（更安全）

2. **Kubeconfig** (`ALIYUN_ACK_KUBECONFIG`):
   - 可以是完整的 kubeconfig YAML 内容
   - 也可以是 base64 编码的内容（workflow 会自动解码）
   - 必须包含访问 ACK 集群的完整配置

3. **访问密钥** (`*_ACCESS_KEY_*`):
   - 从云平台控制台获取
   - 确保密钥有足够的权限（参考部署文档中的权限要求）

---

## 按平台分类

### 仅使用 AWS 平台

**必需 Secrets:**
- `AWS_ACCESS_KEY_ID` (所有环境)
- `AWS_SECRET_ACCESS_KEY` (所有环境)
- `AWS_EC2_SSH_KEY` (仅 test 环境，staging 分支)
- `AWS_EC2_HOST` (仅 test 环境，staging 分支)
- `AWS_EC2_USER` (仅 test 环境，staging 分支)

**注意**: 
- Prod 环境（main 分支）使用 ECS Fargate Serverless，不需要 EC2 相关 Secrets
- Test 环境（staging 分支）使用 EC2 + Docker Compose，需要 EC2 相关 Secrets

**总计**: 5 个 Secrets（如果只部署 prod 环境，只需要前 2 个）

### 仅使用阿里云平台

**必需 Secrets:**
- `ALIYUN_ACCESS_KEY_ID` (所有环境)
- `ALIYUN_ACCESS_KEY_SECRET` (所有环境)
- `ALIYUN_ACK_KUBECONFIG` (仅 prod 环境，main 分支)
- `ALIYUN_ECS_SSH_KEY` (仅 test 环境，staging 分支)
- `ALIYUN_ECS_HOST` (仅 test 环境，staging 分支)
- `ALIYUN_ECS_USER` (仅 test 环境，staging 分支)

**可选 Secrets:**
- `ALIYUN_ACR_REGISTRY`
- `ALIYUN_ACR_NAMESPACE`
- `ALIYUN_ACR_USERNAME`
- `ALIYUN_ACR_PASSWORD`

**注意**: 
- Prod 环境（main 分支）使用 ACK (Kubernetes) Serverless，需要 `ALIYUN_ACK_KUBECONFIG`
- Test 环境（staging 分支）使用 ECS + Docker Compose，需要 ECS 相关 Secrets

**总计**: 6 个必需 + 4 个可选 = 最多 10 个 Secrets（如果只部署一个环境，需要更少）

### 同时使用 AWS 和阿里云平台

**必需 Secrets:**
- AWS 平台的所有必需 Secrets (5 个)
- 阿里云平台的所有必需 Secrets (6 个)

**可选 Secrets:**
- 阿里云 ACR 相关 Secrets (4 个)

**总计**: 11 个必需 + 4 个可选 = 最多 15 个 Secrets

---

## 配置步骤

### 1. 访问 GitHub Secrets 配置页面

1. 打开 GitHub 仓库
2. 点击 **Settings** (设置)
3. 在左侧菜单中找到 **Secrets and variables** → **Actions**
4. 点击 **New repository secret** 按钮

### 2. 配置 AWS Secrets

#### AWS_ACCESS_KEY_ID 和 AWS_SECRET_ACCESS_KEY

1. 登录 AWS 控制台
2. 进入 IAM → Users → 选择用户 → Security credentials
3. 创建 Access Key
4. 复制 Access Key ID 和 Secret Access Key
5. 在 GitHub 中创建对应的 Secret

**权限要求**: 参考 [AWS 部署指南](DEPLOYMENT_AWS.md#前置要求)

#### AWS_EC2_SSH_KEY

1. 生成 SSH 密钥对（如果还没有）:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github-actions-aws
   ```

2. 将公钥添加到 EC2 服务器:
   ```bash
   ssh-copy-id -i ~/.ssh/github-actions-aws.pub ec2-user@<EC2_HOST>
   ```

3. 复制私钥内容到 GitHub Secret:
   ```bash
   cat ~/.ssh/github-actions-aws
   # 复制完整内容（包括 BEGIN 和 END 行）
   ```

#### AWS_EC2_HOST 和 AWS_EC2_USER

- `AWS_EC2_HOST`: EC2 服务器的公网 IP 或域名（如 `184.169.176.3`）
- `AWS_EC2_USER`: SSH 用户名（通常是 `ec2-user` 或 `ubuntu`）

### 3. 配置阿里云 Secrets

#### ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET

1. 登录阿里云控制台
2. 进入 **访问控制 (RAM)** → **用户** → 选择用户 → **安全信息**
3. 创建 AccessKey
4. 复制 AccessKey ID 和 AccessKey Secret
5. 在 GitHub 中创建对应的 Secret

**权限要求**: 参考 [阿里云部署指南](DEPLOYMENT_ALIYUN.md#前置要求)

#### ALIYUN_ACK_KUBECONFIG

1. 登录阿里云控制台
2. 进入 **容器服务 Kubernetes 版 (ACK)** → **集群**
3. 选择集群 → **连接信息**
4. 复制 kubeconfig 内容
5. 在 GitHub 中创建 Secret，值可以是：
   - 直接粘贴 kubeconfig YAML 内容
   - 或 base64 编码后的内容

#### ALIYUN_ECS_SSH_KEY

1. 生成 SSH 密钥对（如果还没有）:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github-actions-aliyun
   ```

2. 将公钥添加到 ECS 服务器:
   ```bash
   ssh-copy-id -i ~/.ssh/github-actions-aliyun.pub root@<ECS_HOST>
   ```

3. 复制私钥内容到 GitHub Secret:
   ```bash
   cat ~/.ssh/github-actions-aliyun
   # 复制完整内容（包括 BEGIN 和 END 行）
   ```

#### ALIYUN_ECS_HOST 和 ALIYUN_ECS_USER

- `ALIYUN_ECS_HOST`: ECS 服务器的公网 IP 或域名（如 `8.134.142.218`）
- `ALIYUN_ECS_USER`: SSH 用户名（通常是 `root` 或 `ecs-user`）

### 4. 配置可选 ACR Secrets（如果使用 ACR）

#### ALIYUN_ACR_REGISTRY

ACR 镜像仓库地址，格式：`registry.cn-<region>.aliyuncs.com`

例如：`registry.cn-hangzhou.aliyuncs.com`

#### ALIYUN_ACR_NAMESPACE

ACR 命名空间，通常是项目名称，如：`knowhere`

#### ALIYUN_ACR_USERNAME 和 ALIYUN_ACR_PASSWORD

1. 登录阿里云控制台
2. 进入 **容器镜像服务 (ACR)** → **访问凭证**
3. 设置固定密码或使用临时密码
4. 用户名通常是阿里云账号或 RAM 用户名

---

## 验证配置

### 检查 Secret 是否配置成功

1. 在 GitHub 仓库的 **Settings** → **Secrets and variables** → **Actions** 页面
2. 确认所有必需的 Secret 都已列出
3. Secret 名称必须**完全匹配**（区分大小写）

### 测试构建和部署

1. 推送到 `staging` 或 `main` 分支
2. 查看 GitHub Actions 运行日志
3. 如果出现认证错误，检查对应的 Secret 是否正确配置

---

## 安全建议

1. **最小权限原则**: 为 GitHub Actions 使用的 AccessKey 配置最小必要权限
2. **定期轮换**: 定期更换 AccessKey 和 SSH 密钥
3. **使用环境 Secrets**: 对于生产环境，考虑使用 GitHub Environments 配置环境特定的 Secrets
4. **审计日志**: 定期检查 GitHub Actions 运行日志，确保没有异常访问
5. **SSH 密钥**: 使用 Ed25519 格式的 SSH 密钥（更安全）

---

## 故障排查

### Secret 未找到错误

**错误信息**: `Secret not found: XXX`

**解决方法**:
1. 检查 Secret 名称是否完全匹配（区分大小写）
2. 确认 Secret 已在仓库中配置
3. 检查是否有拼写错误

### 认证失败错误

**错误信息**: `Authentication failed` 或 `Access denied`

**解决方法**:
1. 验证 AccessKey 是否有效
2. 检查 AccessKey 权限是否足够
3. 确认 Secret 值是否正确（没有多余的空格或换行）

### SSH 连接失败

**错误信息**: `Permission denied (publickey)`

**解决方法**:
1. 确认 SSH 私钥内容完整（包括 BEGIN 和 END 行）
2. 验证公钥已添加到目标服务器
3. 检查 SSH 用户名是否正确

---

## 相关文档

- [GitHub Actions 构建指南](GITHUB_ACTIONS_BUILD.md)
- [AWS 部署指南](DEPLOYMENT_AWS.md)
- [阿里云部署指南](DEPLOYMENT_ALIYUN.md)
- [GitHub Secrets 官方文档](https://docs.github.com/en/actions/security-guides/encrypted-secrets)

---

**最后更新**: 2025-01-XX  
**维护者**: DevOps Team

