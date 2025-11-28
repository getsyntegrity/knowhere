# 服务更新指南

本文档说明如何更新已部署的 ECS 服务，特别是更新 web 服务配置。

## 更新前准备

### 1. 更新本地 .env 文件

确保本地 `.env` 文件包含新的 web 服务配置变量：

```bash
# Web前端服务配置
# API URL（构建时配置，需要 NEXT_PUBLIC_ 前缀）
API_URL=https://apitest.knowhereto.com
NEXT_PUBLIC_API_URL=${API_URL}

# 公司信息配置（运行时动态配置，不带 NEXT_PUBLIC_ 前缀）
# 这些配置通过 /api/config API 动态获取，支持运行时修改
COMPANY_NAME=深圳市渊维科技有限公司
SIMPLE_COMPANY_NAME=渊维科技

# ICP备案信息（国内部署时使用，海外部署可留空）
ICP_NUMBER=
ICP_URL=https://beian.miit.gov.cn/
```

### 2. 确认配置文件已更新

确保以下文件已更新：
- `deploy/aliyun/docker-compose.ecs.yml` - 已包含 web 服务的 env_file 配置
- `deploy/aliyun/scripts/env.template` - 已包含 web 服务配置模板

## 更新步骤

### 方式一：使用部署脚本（推荐）

这是最简单的方式，脚本会自动处理所有步骤：

```bash
cd deploy/aliyun/scripts

# 确保已配置 deploy-config.sh 或设置环境变量
# 如果使用配置文件：
source ../deploy-config.sh

# 执行部署脚本
./deploy-local.sh
```

脚本会：
1. 传输更新的 `docker-compose.ecs.yml` 文件
2. 询问是否更新 `.env` 文件（选择 `y` 更新）
3. 传输部署脚本
4. 在服务器上执行部署，自动拉取镜像并重启服务

### 方式二：手动更新（分步执行）

如果需要更精细的控制，可以手动执行每个步骤：

#### 步骤 1: 传输更新的配置文件

```bash
# 设置服务器信息
export ECS_HOST=your-ecs-ip
export ECS_USER=root
export SSH_KEY=~/.ssh/id_rsa  # 可选

# 传输 docker-compose 文件
scp -i $SSH_KEY deploy/aliyun/docker-compose.ecs.yml \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/docker-compose.ecs.yml

# 传输 .env 文件（包含新的 web 服务配置）
scp -i $SSH_KEY .env \
    ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/.env

# 设置 .env 文件权限
ssh -i $SSH_KEY ${ECS_USER}@${ECS_HOST} \
    "chmod 600 /var/lib/knowhere/.env"
```

#### 步骤 2: 在服务器上执行更新

SSH 到服务器：

```bash
ssh -i $SSH_KEY ${ECS_USER}@${ECS_HOST}
```

在服务器上执行：

```bash
cd /var/lib/knowhere

# 设置 ACR 登录信息（如需要）
export ACR_REGISTRY="knowhere-registry.cn-shenzhen.cr.aliyuncs.com"
export ACR_NAMESPACE="knowhere"
export ALIYUN_ACR_USERNAME="your-username"
export ALIYUN_ACR_PASSWORD="your-password"

# 方式 A: 使用部署脚本（推荐）
/var/lib/knowhere/scripts/deploy-to-ecs.sh

# 方式 B: 手动更新（仅更新 web 服务配置）
# 1. 拉取最新镜像（如果需要）
docker-compose -f docker-compose.ecs.yml pull web

# 2. 强制重新创建 web 服务以应用新的环境变量
docker-compose -f docker-compose.ecs.yml up -d --force-recreate web

# 3. 验证服务状态
docker-compose -f docker-compose.ecs.yml ps web
docker-compose -f docker-compose.ecs.yml logs --tail 50 web
```

## 验证更新

### 1. 检查服务状态

```bash
ssh ${ECS_USER}@${ECS_HOST}
cd /var/lib/knowhere
docker-compose -f docker-compose.ecs.yml ps
```

所有服务应该显示为 `Up` 状态。

### 2. 检查 web 服务环境变量

```bash
# 在服务器上执行
docker exec knowhere-web env | grep -E "COMPANY_NAME|ICP_NUMBER|API_URL"
```

应该能看到：
- `COMPANY_NAME=深圳市渊维科技有限公司`
- `ICP_NUMBER=`（如果设置了）
- `NEXT_PUBLIC_API_URL=https://apitest.knowhereto.com`

### 3. 测试配置 API

访问 web 服务的配置 API：

```bash
curl http://localhost:3000/api/config
```

或者通过域名访问：

```bash
curl https://test.knowhereto.com/api/config
```

应该返回包含公司名称和 ICP 信息的 JSON 配置。

### 4. 检查前端页面

访问前端页面，检查页脚是否显示正确的公司名称和 ICP 备案信息。

## 常见问题

### Q: 更新后 web 服务没有读取到新配置？

**A:** 确保：
1. `.env` 文件已正确传输到服务器
2. `.env` 文件包含所有必要的变量（COMPANY_NAME, ICP_NUMBER 等）
3. web 服务已重新创建（使用 `--force-recreate`）

```bash
# 强制重新创建 web 服务
docker-compose -f docker-compose.ecs.yml up -d --force-recreate web
```

### Q: 如何只更新 web 服务配置，不更新镜像？

**A:** 如果只需要更新环境变量配置，不需要拉取新镜像：

```bash
cd /var/lib/knowhere
docker-compose -f docker-compose.ecs.yml up -d --force-recreate --no-deps web
```

`--no-deps` 参数确保不会重启依赖的服务。

### Q: 更新后服务无法启动？

**A:** 检查服务日志：

```bash
docker-compose -f docker-compose.ecs.yml logs --tail 100 web
```

常见问题：
- `.env` 文件格式错误（缺少引号、特殊字符等）
- 环境变量值包含空格但未加引号
- 文件权限问题

### Q: 如何回滚到之前的配置？

**A:** 如果更新出现问题，可以：

1. 恢复之前的 `.env` 文件
2. 恢复之前的 `docker-compose.ecs.yml` 文件
3. 重新执行部署脚本

或者直接重启服务：

```bash
docker-compose -f docker-compose.ecs.yml restart web
```

## 注意事项

1. **备份 .env 文件**：更新前建议备份服务器上的 `.env` 文件
2. **零停机更新**：`docker-compose up -d` 会进行零停机更新，但建议在低峰期执行
3. **配置验证**：更新后务必验证配置是否正确应用
4. **日志监控**：更新后监控服务日志，确保没有错误

## 快速更新命令（仅更新 web 配置）

如果只需要更新 web 服务的环境变量配置：

```bash
# 1. 传输更新的 .env 文件
scp -i $SSH_KEY .env ${ECS_USER}@${ECS_HOST}:/var/lib/knowhere/.env

# 2. SSH 到服务器并重新创建 web 服务
ssh -i $SSH_KEY ${ECS_USER}@${ECS_HOST} \
    "cd /var/lib/knowhere && \
     docker-compose -f docker-compose.ecs.yml up -d --force-recreate --no-deps web && \
     docker-compose -f docker-compose.ecs.yml logs --tail 50 web"
```
