# 域名配置说明

## 域名与分支映射

| 服务 | 环境 | 域名 | Git分支 |
|------|------|------|---------|
| **API** | prod | `api.knowhereto.com` | main |
| **API** | test | `apitest.knowhereto.com` | test |
| **API** | dev | `apidev.knowhereto.com` | dev |
| **Web** | prod | `knowhereto.com` | main |
| **Web** | test | `test.knowhereto.com` | test |
| **Web** | dev | `dev.knowhereto.com` | dev |

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

### 阿里云 Kubernetes Ingress

Ingress配置使用环境变量：
- `${API_DOMAIN}` - API域名
- `${WEB_DOMAIN}` - Web域名

部署时需要设置：
- dev: `API_DOMAIN=apidev.knowhereto.com`, `WEB_DOMAIN=dev.knowhereto.com`
- test: `API_DOMAIN=apitest.knowhereto.com`, `WEB_DOMAIN=test.knowhereto.com`
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
- Terraform配置：`deploy/aws/terraform/`
- 环境变量模板：`deploy/config/aws/env.template`

### 阿里云
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

