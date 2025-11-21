# 域名配置说明

## 域名与分支映射

| 服务 | 环境 | 域名 | Git分支 | 部署方案 |
|------|------|------|---------|----------|
| **API** | prod | `api.knowhereto.com` | main | Serverless (ECS Fargate/ACK) |
| **API** | test | `apitest.knowhereto.com` | staging | ECS/EC2 + Docker Compose |
| **API** | dev | `apidev.knowhereto.com` | dev | 本地开发（不部署） |
| **Web** | prod | `knowhereto.com` | main | Serverless (ECS Fargate/ACK) |
| **Web** | test | `test.knowhereto.com` | staging | ECS/EC2 + Docker Compose |
| **Web** | dev | `dev.knowhereto.com` | dev | 本地开发（不部署） |

**注意**：
- **test 环境**使用 `staging` 分支，部署到固定的 ECS/EC2 服务器
- **prod 环境**使用 `main` 分支，部署到 Serverless 基础设施
- **dev 环境**不进行远程部署，仅本地开发

---

## 路由配置

### AWS ALB路由规则

| 优先级 | Host Header | 目标服务 |
|--------|-------------|----------|
| 100 | `apidev.knowhereto.com` | 后端服务 |
| 100 | `apitest.knowhereto.com` | 后端服务 |
| 100 | `api.knowhereto.com` | 后端服务 |
| 200 | `dev.knowhereto.com` | 前端服务 |
| 200 | `test.knowhereto.com` | 前端服务 |
| 200 | `knowhereto.com`, `www.knowhereto.com` | 前端服务 |
| default | 其他 | 前端服务（默认） |

### 阿里云路由配置

#### Test 环境（ECS + Docker Compose）

Test 环境使用 Nginx 容器作为反向代理，配置在 `deploy/aliyun/nginx/nginx.conf` 中：
- API 路由：`apitest.knowhereto.com` → `api` 容器
- Web 路由：`test.knowhereto.com` → `web` 容器

#### Prod 环境（ACK Kubernetes Ingress）

Ingress配置使用环境变量：
- `${API_DOMAIN}` - API域名
- `${WEB_DOMAIN}` - Web域名

部署时需要设置：
- prod: `API_DOMAIN=api.knowhereto.com`, `WEB_DOMAIN=knowhereto.com`

---

## SSL证书配置

### AWS ACM证书

每个环境的证书包含以下域名：

**dev环境**：
- 主域名：`knowhereto.com`
- SAN：`apidev.knowhereto.com`, `dev.knowhereto.com`

**test环境**：
- 主域名：`knowhereto.com`
- SAN：`apitest.knowhereto.com`, `test.knowhereto.com`

**prod环境**：
- 主域名：`knowhereto.com`
- SAN：`api.knowhereto.com`, `www.knowhereto.com`

### 阿里云SSL证书

需要在阿里云证书服务中为每个环境申请证书，或使用Let's Encrypt（通过cert-manager）。

---

## 配置文件位置

### AWS

#### Test 环境（EC2）
- Docker Compose配置：`deploy/aws/docker-compose.ec2.yml`（如存在）
- 部署脚本：`deploy/aws/scripts/deploy-to-ec2.sh`
- 环境变量模板：`deploy/config/aws/env.template`

#### Prod 环境（ECS Fargate）
- Terraform配置：`deploy/aws/terraform/`
- 环境变量模板：`deploy/config/aws/env.template`

### 阿里云

#### Test 环境（ECS）
- Docker Compose配置：`deploy/aliyun/docker-compose.ecs.yml`
- 部署脚本：`deploy/aliyun/scripts/deploy-to-ecs.sh`
- 初始化脚本：`deploy/aliyun/scripts/init-ecs.sh`
- 环境变量模板：`deploy/aliyun/.env.staging.template`
- Nginx配置：`deploy/aliyun/nginx/nginx.conf`
- 详细文档：`deploy/aliyun/README.md`

#### Prod 环境（ACK Kubernetes）
- Terraform配置：`deploy/aliyun/ack/terraform/`
- Kubernetes配置：`deploy/aliyun/ack/kubernetes/`
- 环境变量模板：`deploy/config/aliyun/env.template`

---

## 部署前检查

- [ ] 确认Route53托管区域 `knowhereto.com` 存在（AWS）
- [ ] 确认阿里云DNS托管区域 `knowhereto.com` 存在
- [ ] 确认所有环境的SSL证书可以正确申请和验证
- [ ] 确认Kubernetes部署脚本中设置了正确的环境变量

---

## 部署后验证

- [ ] DNS解析正确（`apidev.knowhereto.com` → ALB/SLB IP）
- [ ] SSL证书有效（HTTPS可以访问）
- [ ] API路由正确（`apidev.knowhereto.com` → 后端服务）
- [ ] Web路由正确（`dev.knowhereto.com` → 前端服务）
- [ ] S3/OSS事件通知正常工作
- [ ] 前端可以正确调用API（NEXT_PUBLIC_API_URL正确）

