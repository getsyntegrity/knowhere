# 阿里云 ECS 部署脚本

## 概述

`deploy-to-ecs.sh` 用于将应用部署到阿里云 ECS 固定服务器。脚本支持 ACR（阿里云容器镜像服务）和 GHCR（GitHub Container Registry）两种镜像仓库。

## 功能特性

- ✅ 支持 ACR 和 GHCR 两种镜像仓库（优先使用 ACR）
- ✅ 自动 SSH 密钥权限检查和修复
- ✅ 智能镜像标签回退机制
- ✅ 容器健康检查
- ✅ 自动清理未使用的镜像

## 使用方法

### 环境变量

#### 必需变量

- `ECS_HOST`: ECS 服务器地址（IP 或域名）
- `ECS_USER`: SSH 用户名（默认：root）
- `IMAGE_TAG`: 镜像标签（例如：`staging-latest`）

#### ACR 配置（推荐）

- `ACR_REGISTRY`: ACR registry 地址（例如：`knowhere-registry.cn-shenzhen.cr.aliyuncs.com`）
- `ACR_NAMESPACE`: ACR 命名空间（默认：`knowhere`）
- `ALIYUN_ACR_USERNAME`: ACR 用户名
- `ALIYUN_ACR_PASSWORD`: ACR 密码

#### GHCR 配置（备选）

- `GITHUB_USERNAME`: GitHub 用户名
- `GITHUB_TOKEN`: GitHub token（可选，如果服务器已配置可省略）

#### 可选变量

- `SSH_KEY`: SSH 私钥文件路径（如果未设置，使用默认 SSH 配置）

### 使用示例

#### 使用 ACR

```bash
export ECS_HOST="your-ecs-host"
export ECS_USER="root"
export IMAGE_TAG="staging-latest"
export ACR_REGISTRY="knowhere-registry.cn-shenzhen.cr.aliyuncs.com"
export ACR_NAMESPACE="knowhere"
export ALIYUN_ACR_USERNAME="your-username"
export ALIYUN_ACR_PASSWORD="your-password"
export SSH_KEY="./id_rsa"  # 可选

./deploy-to-ecs.sh
```

#### 使用 GHCR

```bash
export ECS_HOST="your-ecs-host"
export ECS_USER="root"
export IMAGE_TAG="staging-latest"
export GITHUB_USERNAME="your-github-username"
export GITHUB_TOKEN="your-token"  # 可选
export SSH_KEY="./id_rsa"  # 可选

./deploy-to-ecs.sh
```

## 部署流程

1. **环境检查**：验证必需的环境变量
2. **SSH 连接**：检查并修复 SSH 密钥权限
3. **镜像仓库选择**：优先使用 ACR，否则使用 GHCR
4. **服务部署**（每个服务）：
   - 登录镜像仓库
   - 停止并删除旧容器
   - 拉取新镜像（支持智能标签回退）
   - 启动新容器
   - 检查容器状态
   - 清理未使用的镜像

## 镜像标签回退机制

如果指定的镜像标签不存在，脚本会根据环境自动尝试备用标签：

- **dev 环境**：`dev-latest` → `staging-latest` → `latest`
- **staging 环境**：`staging-latest` → `dev-latest` → `latest`
- **prod/main 环境**：`main-latest` → `prod-latest` → `latest`
- **其他**：`staging-latest` → `dev-latest` → `latest`

## 部署的服务

- **后端服务**：`knowhere-backend`（端口：5005）
- **前端服务**：`knowhere-frontend`（端口：3000）
- **Worker 服务**：`knowhere-worker`（端口：8000，默认禁用）

## 验证部署

部署完成后，可以使用以下命令验证：

```bash
# 检查容器状态
ssh ${ECS_USER}@${ECS_HOST} 'docker ps'

# 查看后端日志
ssh ${ECS_USER}@${ECS_HOST} 'docker logs knowhere-backend --tail 50'

# 查看前端日志
ssh ${ECS_USER}@${ECS_HOST} 'docker logs knowhere-frontend --tail 50'

# 测试服务
curl http://${ECS_HOST}:5005/health  # 后端健康检查
curl http://${ECS_HOST}:3000          # 前端
```

## 故障排查

### SSH 连接失败

```bash
# 检查 SSH 密钥权限
chmod 600 ${SSH_KEY}

# 测试 SSH 连接
ssh -i ${SSH_KEY} ${ECS_USER}@${ECS_HOST} "echo '连接成功'"
```

### 镜像拉取失败

```bash
# 检查镜像仓库登录
ssh ${ECS_USER}@${ECS_HOST} "docker login ${ACR_REGISTRY} -u ${ALIYUN_ACR_USERNAME} -p ${ALIYUN_ACR_PASSWORD}"

# 手动拉取镜像测试
ssh ${ECS_USER}@${ECS_HOST} "docker pull ${ACR_REGISTRY}/${ACR_NAMESPACE}/knowhere-backend:${IMAGE_TAG}"
```

### 容器启动失败

```bash
# 查看容器日志
ssh ${ECS_USER}@${ECS_HOST} "docker logs knowhere-backend"

# 检查端口占用
ssh ${ECS_USER}@${ECS_HOST} "netstat -tuln | grep -E '5005|3000'"
```

## 注意事项

1. **SSH 密钥权限**：脚本会自动检查和修复 SSH 密钥权限（600），如果无法修改，请手动执行 `chmod 600 <key-file>`
2. **镜像仓库登录**：如果服务器上已保存登录凭证，脚本会跳过登录步骤
3. **容器配置**：当前脚本使用基本配置（端口映射、自动重启），如需环境变量、卷挂载等，请修改 `docker run` 命令
4. **镜像清理**：脚本会清理 24 小时前未使用的镜像，保留最近使用的镜像

## 与 GitHub Actions 集成

此脚本已集成到 `.github/workflows/deploy-aliyun-ack.yml` 中，当代码推送到 `staging` 分支时会自动触发部署。

