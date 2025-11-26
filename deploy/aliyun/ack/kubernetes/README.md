# Kubernetes 部署指南 - 阿里云 ACK

## 环境配置

### 域名配置

根据环境自动设置域名：

| 环境 | API域名 | Web域名 | Git分支 |
|------|---------|---------|---------|
| dev | `apidev.knowhereto.com` | `dev.knowhereto.com` | dev |
| test | `apitest.knowhereto.com` | `test.knowhereto.com` | test |
| prod | `api.knowhereto.com` | `knowhereto.com` | main |

### 分支与环境映射

- **main 分支** → **prod 环境** → `api.knowhereto.com` / `knowhereto.com`
- **test 分支** → **test 环境** → `apitest.knowhereto.com` / `test.knowhereto.com`
- **dev 分支** → **dev 环境** → `apidev.knowhereto.com` / `dev.knowhereto.com`

## 部署步骤

### 1. 准备环境变量

根据环境设置环境变量：

```bash
# 开发环境
export ENVIRONMENT=dev
export API_DOMAIN=apidev.knowhereto.com
export WEB_DOMAIN=dev.knowhereto.com
export API_URL=https://apidev.knowhereto.com
export REGISTRY=registry.cn-hangzhou.aliyuncs.com
export NAMESPACE=knowhere
export APP_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null || echo "dev-$(git rev-parse --short HEAD)")

# 测试环境
export ENVIRONMENT=test
export API_DOMAIN=apitest.knowhereto.com
export WEB_DOMAIN=test.knowhereto.com
export API_URL=https://apitest.knowhereto.com
# ... 其他变量

# 生产环境
export ENVIRONMENT=prod
export API_DOMAIN=api.knowhereto.com
export WEB_DOMAIN=knowhereto.com
export API_URL=https://api.knowhereto.com
# ... 其他变量
```

### 2. 部署 Kubernetes 资源

使用部署脚本自动部署：

```bash
cd deploy/aliyun/ack/scripts
export ENVIRONMENT=dev  # 或 test/prod
./deploy-k8s.sh
```

脚本会自动：
- 根据环境设置正确的域名
- 替换 Kubernetes 配置文件中的环境变量占位符
- 应用所有资源到集群

### 3. 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -n knowhere

# 检查 Ingress
kubectl get ingress -n knowhere

# 检查服务
kubectl get svc -n knowhere
```

## 配置文件说明

### 基础配置

`base/` 目录包含所有环境的通用配置：
- `namespace.yaml` - 命名空间
- `configmap.yaml` - ConfigMap（使用环境变量占位符）
- `secrets.yaml` - Secrets 模板（需要手动设置实际值）
- `service.yaml` - Service 定义
- `deployment-api.yaml` - API 服务部署
- `deployment-web.yaml` - Web 服务部署
- `deployment-worker.yaml` - Worker 服务部署
- `ingress.yaml` - Ingress 配置（使用环境变量占位符）
- `pvc-model-cache.yaml` - 模型缓存 PVC

### 环境特定配置

`dev/`, `test/`, `prod/` 目录包含环境特定的配置（如 kustomization.yaml）。

## 环境变量占位符

以下环境变量会在部署时被替换：

- `${ENVIRONMENT}` - 环境名称（dev/test/prod）
- `${API_DOMAIN}` - API 域名
- `${WEB_DOMAIN}` - Web 域名
- `${API_URL}` - API 完整 URL
- `${REGISTRY}` - 容器镜像仓库地址
- `${NAMESPACE}` - Kubernetes 命名空间
- `${API_REPLICAS}` - API 服务副本数（默认：2）
- `${WEB_REPLICAS}` - Web 服务副本数（默认：2）
- `${WORKER_REPLICAS}` - Worker 服务副本数（默认：1）
- `${APP_VERSION}` - 应用版本号
- `${OSS_BUCKET_NAME}` - OSS 存储桶名称

## 注意事项

1. **Secrets 管理**：部署前需要先创建 Kubernetes Secrets，参考 `base/secrets.yaml` 中的说明
2. **镜像构建**：确保已使用 `build-and-push.sh` 构建并推送镜像到容器镜像服务
3. **DNS 配置**：确保 DNS 记录已正确配置，指向 Ingress Controller 的 LoadBalancer IP
4. **SSL 证书**：确保已配置 SSL 证书（推荐使用阿里云证书文件，参考 `HTTPS_CERTIFICATE_CONFIG.md`）

## 故障排查

### Pod 无法启动

```bash
# 查看 Pod 日志
kubectl logs -n knowhere <pod-name>

# 查看 Pod 事件
kubectl describe pod -n knowhere <pod-name>
```

### Ingress 无法访问

```bash
# 检查 Ingress 配置
kubectl describe ingress -n knowhere knowhere-ingress

# 检查 Ingress Controller
kubectl get pods -n ingress-nginx
```

### 环境变量未正确替换

确保部署脚本正确设置了所有必需的环境变量，并检查 `deploy-k8s.sh` 脚本的输出日志。

### HTTPS 证书配置

如果 HTTPS 无法访问，请检查：

```bash
# 检查 TLS Secret 是否存在
kubectl get secret knowhere-tls -n knowhere

# 检查 Ingress 配置
kubectl describe ingress knowhere-ingress -n knowhere

# 查看证书配置文档
cat ../HTTPS_CERTIFICATE_CONFIG.md
```

详细配置说明请参考 `HTTPS_CERTIFICATE_CONFIG.md`。

