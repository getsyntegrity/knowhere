# AWS EC2 Docker Compose 部署文档

> **重要说明**：本文档仅适用于 **test 环境（staging 分支）** 的部署。
> 
> - **Test 环境**：使用本方案（EC2 + Docker Compose）
> - **Prod 环境**：使用 ECS Fargate Serverless 方案，请参考 [AWS 部署指南](../DEPLOYMENT_AWS.md)

本文档说明如何在 AWS EC2 服务器上使用 Docker Compose 部署 Knowhere 应用的 test 环境。

## 架构概述

部署包含以下服务：

- **api**: 后端 API 服务（FastAPI）
- **web**: 前端 Web 服务（Next.js）
- **worker**: 异步任务处理服务（Celery）
- **postgres**: PostgreSQL 数据库
- **redis**: Redis 缓存
- **rabbitmq**: RabbitMQ 消息队列
- **nginx**: Nginx 反向代理和 SSL 终端

所有服务通过 Docker Compose 管理，数据持久化到 `/var/lib/knowhere/` 目录。

## 前置要求

### 服务器要求

- AWS EC2 实例
- 操作系统: Linux (Ubuntu/Amazon Linux 2 等)
- 已安装 Docker 和 docker-compose
- 至少 4GB 内存，20GB 磁盘空间
- 开放端口: 80 (HTTP), 443 (HTTPS)
- 安全组配置：允许 80 和 443 端口入站流量

### 域名要求

- 域名已解析到 EC2 服务器公网 IP
- API 域名: `apitest.knowhereto.ai`
- Web 域名: `test.knowhereto.ai`

### 本地要求

- 本地已配置 SSH 访问 EC2 服务器
- 已准备环境变量文件 `.env`
- 已准备部署配置文件 `deploy-config.sh`（可选，推荐）

## 首次部署流程

### 0. 准备部署配置文件（推荐）

为了简化部署流程，避免每次手动设置环境变量，可以创建部署配置文件：

```bash
cd deploy/aws
cp deploy-config.sh.example deploy-config.sh
```

编辑 `deploy-config.sh` 文件，填写实际配置值：

- `EC2_HOST`: EC2 服务器 IP 地址或域名
- `EC2_USER`: SSH 用户名（通常是 `ec2-user` 或 `ubuntu`）
- `SSH_KEY`: SSH 私钥路径（可选）
- `GITHUB_USERNAME`: GitHub 用户名（用于镜像拉取）
- `GITHUB_TOKEN`: GitHub Personal Access Token（用于 GHCR 登录，可选）
- `SSL_DOMAINS`: SSL 证书域名（空格分隔）
- `SSL_EMAIL`: SSL 证书邮箱

**注意**: `deploy-config.sh` 包含敏感信息，不会被提交到 git。如果未创建此文件，脚本会提示手动设置环境变量。

### 1. 准备环境变量文件

基于模板创建 `.env` 文件：

```bash
cp deploy/aws/.env.staging.template .env
```

编辑 `.env` 文件，填写实际配置值：

- 数据库密码: `POSTGRES_PASSWORD`
- Redis 配置（容器内使用默认值）
- RabbitMQ 配置（容器内使用默认值）
- S3 配置（AWS S3 访问密钥）
- 其他应用配置

**重要配置项**:
- `DATABASE_URL`: 使用容器名称 `postgres` 作为主机名
- `REDIS_HOST`: 使用容器名称 `redis`（不是 `localhost`）
- `CELERY_RESULT_BACKEND`: 使用 `redis://redis:6379/2`（不是 `redis://localhost:6379/2`）
- `RABBITMQ_HOST`: 使用容器名称 `rabbitmq`（不是 `localhost`）
- `CELERY_BROKER_URL`: 使用 `amqp://admin:password@rabbitmq:5672//`（不是 `localhost`）

### 2. 初始化 EC2 环境

在本地执行初始化脚本：

**方式一：使用配置文件（推荐）**

如果已创建 `deploy-config.sh` 配置文件：

```bash
cd deploy/aws/scripts
./init-ec2.sh
```

脚本会自动加载 `deploy-config.sh` 中的配置。

**方式二：手动设置环境变量**

如果未创建配置文件，需要手动设置：

```bash
export EC2_HOST=your-ec2-ip
export EC2_USER=ec2-user  # 或 ubuntu，取决于 AMI
export SSH_KEY=~/.ssh/id_rsa  # 可选

cd deploy/aws/scripts
./init-ec2.sh
```

此脚本会：
- 创建必要的目录结构
- 传输 docker-compose 和 nginx 配置文件
- 传输部署脚本
- 检查并安装 Docker 和 docker-compose

### 3. 传输环境变量文件

将准备好的 `.env` 文件传输到服务器：

```bash
scp .env ${EC2_USER}@${EC2_HOST}:/var/lib/knowhere/.env
ssh ${EC2_USER}@${EC2_HOST} "chmod 600 /var/lib/knowhere/.env"
```

### 4. 获取 SSL 证书

SSH 到服务器并执行 SSL 证书获取脚本：

**方式一：使用配置文件**

如果 `deploy-config.sh` 中已配置 `SSL_DOMAINS` 和 `SSL_EMAIL`，可以直接执行：

```bash
ssh ${EC2_USER}@${EC2_HOST}
/var/lib/knowhere/scripts/setup-ssl.sh
```

**方式二：手动设置环境变量**

```bash
ssh ${EC2_USER}@${EC2_HOST}

# 设置域名（如需要）
export SSL_DOMAINS="apitest.knowhereto.ai test.knowhereto.ai"
export SSL_EMAIL="admin@knowhereto.ai"

# 执行证书获取
/var/lib/knowhere/scripts/setup-ssl.sh
```

**注意**: 
- 证书获取需要域名已正确解析到服务器 IP
- 80 端口必须可访问
- 如果 nginx 正在运行，脚本会自动停止它

### 5. 启动所有服务

在服务器上执行部署脚本：

**方式一：使用本地部署脚本（推荐，自动传递配置）**

如果已创建 `deploy-config.sh` 配置文件，在本地执行：

```bash
cd deploy/aws/scripts
./deploy-local.sh
```

脚本会自动加载配置并传递 GitHub 登录信息到服务器。

**方式二：在服务器上手动执行**

```bash
ssh ${EC2_USER}@${EC2_HOST}

# 设置 GitHub 登录信息（如需要）
export GITHUB_USERNAME="your-github-username"
export GITHUB_TOKEN="your-github-token"  # GitHub Personal Access Token

# 执行部署
/var/lib/knowhere/scripts/deploy-to-ec2.sh
```

### 6. 设置 SSL 证书自动续期

设置 cron 任务自动续期证书：

```bash
ssh ${EC2_USER}@${EC2_HOST}

# 编辑 crontab
crontab -e

# 添加以下行（每天凌晨 2 点检查并续期）
0 2 * * * /var/lib/knowhere/scripts/renew-ssl.sh >> /var/log/knowhere-ssl-renew.log 2>&1
```

## 日常部署流程

### 方式一: 使用本地部署脚本（推荐）

**使用配置文件（推荐）**

如果已创建 `deploy-config.sh` 配置文件：

```bash
cd deploy/aws/scripts
./deploy-local.sh
```

脚本会自动加载配置文件中的所有设置。

**手动设置环境变量**

如果未创建配置文件：

```bash
export EC2_HOST=your-ec2-ip
export EC2_USER=ec2-user
export SSH_KEY=~/.ssh/id_rsa  # 可选
export GITHUB_USERNAME="your-github-username"
export GITHUB_TOKEN="your-github-token"  # 可选

cd deploy/aws/scripts
./deploy-local.sh
```

此脚本会：
- 传输更新的配置文件到服务器
- 在服务器上执行部署脚本
- 显示服务状态

### 方式二: 直接 SSH 执行

SSH 到服务器并执行：

```bash
ssh ${EC2_USER}@${EC2_HOST}

# 设置 GitHub 登录信息（如需要）
export GITHUB_USERNAME="your-github-username"
export GITHUB_TOKEN="your-github-token"

# 执行部署
/var/lib/knowhere/scripts/deploy-to-ec2.sh
```

## 服务管理

### 查看服务状态

```bash
cd /var/lib/knowhere
docker-compose -f docker-compose.ec2.yml ps
```

### 查看服务日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.ec2.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.ec2.yml logs -f api
docker-compose -f docker-compose.ec2.yml logs -f web
docker-compose -f docker-compose.ec2.yml logs -f worker
```

### 重启服务

```bash
# 重启所有服务
docker-compose -f docker-compose.ec2.yml restart

# 重启特定服务
docker-compose -f docker-compose.ec2.yml restart api
```

### 停止服务

```bash
# 停止所有服务
docker-compose -f docker-compose.ec2.yml down

# 停止并删除数据卷（谨慎使用）
docker-compose -f docker-compose.ec2.yml down -v
```

### 更新服务

```bash
# 拉取最新镜像并重启
docker-compose -f docker-compose.ec2.yml pull
docker-compose -f docker-compose.ec2.yml up -d
```

## 数据备份和恢复

### 备份数据库

```bash
# 在服务器上执行
docker exec knowhere-postgres pg_dump -U root Knowhere > /var/lib/knowhere/backup_$(date +%Y%m%d_%H%M%S).sql
```

### 恢复数据库

```bash
# 在服务器上执行
docker exec -i knowhere-postgres psql -U root Knowhere < /var/lib/knowhere/backup_20240101_120000.sql
```

### 备份数据目录

```bash
# 备份整个数据目录
tar -czf /tmp/knowhere_backup_$(date +%Y%m%d_%H%M%S).tar.gz /var/lib/knowhere/data
```

## 故障排查

### 服务无法启动

1. 检查服务日志：
   ```bash
   docker-compose -f docker-compose.ec2.yml logs [服务名]
   ```

2. 检查容器状态：
   ```bash
   docker ps -a
   ```

3. 检查环境变量文件：
   ```bash
   cat /var/lib/knowhere/.env
   ```

### SSL 证书问题

1. 检查证书文件：
   ```bash
   ls -la /etc/letsencrypt/live/
   ```

2. 手动续期证书：
   ```bash
   /var/lib/knowhere/scripts/renew-ssl.sh
   ```

3. 重新获取证书：
   ```bash
   /var/lib/knowhere/scripts/setup-ssl.sh
   ```

### 网络连接问题

1. 检查服务间网络：
   ```bash
   docker network inspect knowhere-network
   ```

2. 测试服务连接：
   ```bash
   docker exec knowhere-api ping -c 3 postgres
   docker exec knowhere-api ping -c 3 redis
   ```

### 镜像拉取失败

1. 检查 GitHub Container Registry 登录：
   ```bash
   docker login ghcr.io -u your-username
   ```

2. 验证镜像是否存在：
   ```bash
   docker pull ghcr.io/your-username/knowhere-backend:staging-latest
   ```

### 磁盘空间不足

1. 清理未使用的镜像：
   ```bash
   docker image prune -a
   ```

2. 清理未使用的容器和卷：
   ```bash
   docker system prune -a --volumes
   ```

## 目录结构

```
/var/lib/knowhere/
├── docker-compose.ec2.yml    # Docker Compose 配置文件
├── .env                       # 环境变量文件
├── data/                      # 数据目录
│   ├── postgres/              # PostgreSQL 数据
│   ├── redis/                 # Redis 数据
│   └── rabbitmq/              # RabbitMQ 数据
├── logs/                      # 应用日志
├── nginx/                     # Nginx 配置
│   └── nginx.conf
└── scripts/                   # 部署脚本
    ├── deploy-to-ec2.sh
    ├── setup-ssl.sh
    └── renew-ssl.sh
```

## 安全建议

1. **环境变量文件**: 确保 `.env` 文件权限为 600
   ```bash
   chmod 600 /var/lib/knowhere/.env
   ```

2. **部署配置文件**: 确保 `deploy-config.sh` 文件权限为 600（如果使用）
   ```bash
   chmod 600 deploy/aws/deploy-config.sh
   ```

3. **SSH 访问**: 使用 SSH 密钥认证，禁用密码登录

4. **安全组**: 只开放必要的端口（80, 443, 22）

5. **定期更新**: 定期更新 Docker 镜像和系统包

6. **监控**: 设置 CloudWatch 监控和告警，及时发现异常

## 常见问题

### Q: 如何更改镜像标签？

A: 编辑 `docker-compose.ec2.yml` 文件中的镜像标签，然后重新部署。

### Q: 如何添加新的环境变量？

A: 编辑 `/var/lib/knowhere/.env` 文件，添加新的环境变量，然后重启相关服务。

### Q: 如何查看服务健康状态？

A: 使用 `docker-compose ps` 查看服务状态，或访问健康检查端点：
- API: `https://apitest.knowhereto.ai/health`
- Web: `https://test.knowhereto.ai/health`

### Q: 证书续期失败怎么办？

A: 检查域名解析和 80 端口访问，手动执行续期脚本，查看详细错误信息。

### Q: 如何使用配置文件而不是每次手动 export？

A: 复制 `deploy-config.sh.example` 为 `deploy-config.sh`，填写实际配置值。脚本会自动加载配置文件中的环境变量，无需每次手动设置。配置文件不会被提交到 git，包含敏感信息。

### Q: GitHub Container Registry 登录失败怎么办？

A: 确保在服务器上配置了 GitHub Personal Access Token，或使用 `docker login ghcr.io` 手动登录。

## 联系支持

如遇到问题，请查看日志文件或联系技术支持。

