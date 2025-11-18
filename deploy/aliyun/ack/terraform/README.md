# Terraform 多环境配置指南 - 阿里云

## 环境配置文件

项目支持三个环境，每个环境有独立的配置文件：

- `terraform.tfvars.dev` - 开发环境配置
- `terraform.tfvars.test` - 测试环境配置  
- `terraform.tfvars.prod` - 生产环境配置

**注意**：这些文件包含敏感信息（密码、密钥等），已添加到 `.gitignore`，不会提交到版本控制。

## Terraform State 管理

### 为什么需要为不同环境使用不同的 State？

`terraform.tfstate` 文件记录了 Terraform 管理的所有资源的实际状态。**每个环境必须使用独立的 state**，原因如下：

1. **避免资源冲突**：不同环境的资源会互相干扰
2. **防止误操作**：修改 dev 环境不会影响 prod 环境
3. **状态隔离**：每个环境的状态完全独立，便于管理

### Backend 配置（推荐）

**强烈建议使用 OSS Backend**，而不是本地 state 文件：

- ✅ **远程存储**：State 存储在 OSS，团队成员可以共享
- ✅ **状态锁定**：OSS 支持状态锁定，防止并发修改
- ✅ **版本控制**：OSS 支持版本控制，可以恢复历史状态
- ✅ **加密存储**：State 文件自动加密，保护敏感信息

### 初始化 Backend

**首次使用前，需要先创建 Backend 资源（OSS Bucket）：**

```bash
# 初始化开发环境的 Backend
cd deploy/aliyun/ack/terraform/scripts
./init-backend.sh dev

# 初始化测试环境的 Backend
./init-backend.sh test

# 初始化生产环境的 Backend
./init-backend.sh prod
```

脚本会自动创建：
- OSS Bucket：`knowhere-terraform-state-{environment}`

### 配置 Backend

1. **复制 Backend 配置文件**：

```bash
cd deploy/aliyun/ack/terraform

# 开发环境
cp backend-config.dev.example backend-config.dev
# 编辑 backend-config.dev，确认区域和配置正确

# 测试环境
cp backend-config.test.example backend-config.test

# 生产环境
cp backend-config.prod.example backend-config.prod
```

2. **初始化 Terraform（使用 Backend）**：

```bash
# 开发环境
terraform init -backend-config=backend-config.dev

# 测试环境
terraform init -backend-config=backend-config.test

# 生产环境
terraform init -backend-config=backend-config.prod
```

**注意**：
- `backend-config.*` 文件包含环境特定的配置，已添加到 `.gitignore`
- 每次切换环境时，需要重新运行 `terraform init -backend-config=...`

## 使用方法

### 1. 初始化配置文件

首次使用时，需要复制示例文件并填入实际值：

```bash
# 开发环境
cp terraform.tfvars.example terraform.tfvars.dev
# 编辑 terraform.tfvars.dev，填入开发环境的实际值

# 测试环境
cp terraform.tfvars.example terraform.tfvars.test
# 编辑 terraform.tfvars.test，填入测试环境的实际值

# 生产环境
cp terraform.tfvars.example terraform.tfvars.prod
# 编辑 terraform.tfvars.prod，填入生产环境的实际值
```

### 2. 初始化 Terraform（使用 Backend）

**首次部署或切换环境时，必须先初始化 Backend：**

```bash
# 开发环境
terraform init -backend-config=backend-config.dev

# 测试环境
terraform init -backend-config=backend-config.test

# 生产环境
terraform init -backend-config=backend-config.prod
```

### 3. 部署特定环境

使用 `-var-file` 参数指定要使用的配置文件，并通过命令行自动获取版本号：

```bash
# 部署开发环境（dev/test分支通常没有Tag，使用commit hash）
# 注意：确保已运行 terraform init -backend-config=backend-config.dev
terraform plan \
  -var-file=terraform.tfvars.dev \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'dev-$(git rev-parse --short HEAD)')"
terraform apply \
  -var-file=terraform.tfvars.dev \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'dev-$(git rev-parse --short HEAD)')"

# 部署测试环境
terraform plan \
  -var-file=terraform.tfvars.test \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'test-$(git rev-parse --short HEAD)')"
terraform apply \
  -var-file=terraform.tfvars.test \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || echo 'test-$(git rev-parse --short HEAD)')"

# 部署生产环境（main分支应该有Tag）
terraform plan \
  -var-file=terraform.tfvars.prod \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || git describe --tags HEAD 2>/dev/null || echo 'prod-$(git rev-parse --short HEAD)')"
terraform apply \
  -var-file=terraform.tfvars.prod \
  -var="app_version=$(git describe --tags --exact-match HEAD 2>/dev/null || git describe --tags HEAD 2>/dev/null || echo 'prod-$(git rev-parse --short HEAD)')"
```

**推荐方式**：使用部署脚本，脚本会自动获取版本号：

```bash
# 部署开发环境
cd ../scripts
export ENVIRONMENT=dev
export REGION=cn-guangzhou
./deploy.sh all

# 部署测试环境
export ENVIRONMENT=test
./deploy.sh all

# 部署生产环境
export ENVIRONMENT=prod
./deploy.sh all
```

### 4. 版本号自动获取说明

版本号获取规则：
- **dev/test 分支**：通常没有 Tag，使用 `环境名-commit hash`（如 `dev-abc1234`）
- **prod 分支（main）**：应该有 Git Tag，使用 Tag（如 `v1.0.0`）

部署脚本会自动根据当前 Git 状态获取版本号：
- 如果有精确匹配的 Tag → 使用 Tag（如 `v1.0.0`）
- 如果有 Tag 但不是精确匹配 → 使用 Tag+commit hash（如 `v1.0.0-abc1234`）
- 如果没有 Tag → 使用 `环境名-commit hash`（如 `dev-abc1234`）

## 环境变量说明

每个环境的配置文件需要设置以下变量：

### 必需变量（无默认值，必须设置）

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `access_key` | 阿里云AccessKey ID | `LTAI5t...` |
| `secret_key` | 阿里云AccessKey Secret | `xxx...` |
| `domain_name` | 域名 | `knowhereto.com` |
| `db_password` | 数据库密码 | 强密码字符串 |
| `rabbitmq_password` | RabbitMQ密码 | 强密码字符串 |

### 基础配置变量（有默认值，但建议明确设置）

| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| `region` | 阿里云区域 | `cn-guangzhou` | `cn-guangzhou`（华南3-广州） |
| `project_name` | 项目名称 | `knowhere` | `knowhere` |
| `environment` | 环境名称 | `dev` | `dev` / `test` / `prod` |
| `app_version` | 应用版本号 | `dev` | **建议通过命令行自动获取，不要在此文件中设置** |
| `rabbitmq_username` | RabbitMQ用户名 | `admin` | `admin` |
| `api_webhook_endpoint` | API Webhook端点 | `""` | `https://apidev.knowhereto.com/v1/internal/oss-events` |

### Secrets 变量（敏感信息，建议设置）

| 变量名 | 说明 | 默认值 | 是否必需 |
|--------|------|--------|---------|
| `oss_access_key_id` | OSS访问密钥ID | `""` | 是（应用需要访问OSS） |
| `oss_secret_access_key` | OSS秘密访问密钥 | `""` | 是（应用需要访问OSS） |

**注意**：OSS桶名会根据环境自动生成，格式为：`{project_name}-{environment}-storage-{8位随机字符串}`

- dev环境：`knowhere-dev-storage-xxxxxxxx`
- test环境：`knowhere-test-storage-xxxxxxxx`
- prod环境：`knowhere-prod-storage-xxxxxxxx`

部署后可通过以下命令查看实际桶名：
```bash
terraform output oss_bucket_name
```

| `app_secret_key` | 应用JWT密钥 | `""` | 是（用于token签名） |
| `stripe_secret_key` | Stripe密钥 | `""` | 否（支付功能需要） |
| `stripe_publishable_key` | Stripe发布密钥 | `""` | 否（支付功能需要） |
| `posthog_key` | PostHog密钥 | `""` | 否（分析功能需要） |

**注意**：如果 Secrets 变量留空，secret 会被创建但值为空，需要后续手动设置（通过Kubernetes Secrets）。

## 环境差异

不同环境在资源创建时会有以下差异：

### 开发环境 (dev)
- **域名**：`apidev.knowhereto.com`, `dev.knowhereto.com`
- **API Webhook端点**：`https://apidev.knowhereto.com/v1/internal/oss-events`
- **ACK集群工作节点数**：2
- **RDS实例**：1
- **RabbitMQ**：Serverless，max_tps=1000，max_connections=500
- **日志保留**：7天
- **删除保护**：关闭（RDS）
- **OSS桶名**：`knowhere-dev-storage-xxxxxxxx`（自动生成）

### 测试环境 (test)
- **域名**：`apitest.knowhereto.com`, `test.knowhereto.com`
- **API Webhook端点**：`https://apitest.knowhereto.com/v1/internal/oss-events`
- **ACK集群工作节点数**：2
- **RDS实例**：1
- **RabbitMQ**：Serverless，max_tps=1000，max_connections=500
- **日志保留**：7天
- **删除保护**：关闭（RDS）
- **OSS桶名**：`knowhere-test-storage-xxxxxxxx`（自动生成）

### 生产环境 (prod)
- **域名**：`api.knowhereto.com`, `knowhereto.com`
- **API Webhook端点**：`https://api.knowhereto.com/v1/internal/oss-events`
- **ACK集群工作节点数**：3
- **RDS实例**：1（高可用配置）
- **RabbitMQ**：Serverless，max_tps=5000，max_connections=1000
- **日志保留**：30天
- **删除保护**：开启（RDS）
- **OSS桶名**：`knowhere-prod-storage-xxxxxxxx`（自动生成）

### 根据环境需要配置的变量

以下变量**必须**在不同环境中设置不同的值：

| 变量名 | dev环境 | test环境 | prod环境 |
|--------|---------|----------|----------|
| `access_key` | 开发AccessKey | 测试AccessKey | 生产AccessKey |
| `secret_key` | 开发SecretKey | 测试SecretKey | 生产SecretKey |
| `domain_name` | 开发域名 | 测试域名 | 生产域名 |
| `db_password` | 开发数据库密码 | 测试数据库密码 | 生产数据库密码 |
| `rabbitmq_password` | 开发RabbitMQ密码 | 测试RabbitMQ密码 | 生产RabbitMQ密码 |
| `api_webhook_endpoint` | `https://apidev.knowhereto.com/v1/internal/oss-events` | `https://apitest.knowhereto.com/v1/internal/oss-events` | `https://api.knowhereto.com/v1/internal/oss-events` |
| `oss_access_key_id` | 开发OSS密钥 | 测试OSS密钥 | 生产OSS密钥 |
| `oss_secret_access_key` | 开发OSS密钥 | 测试OSS密钥 | 生产OSS密钥 |
| `app_secret_key` | 开发JWT密钥 | 测试JWT密钥 | 生产JWT密钥 |

以下变量**建议**在不同环境中设置不同的值（但可以使用相同值）：

| 变量名 | 说明 |
|--------|------|
| `region` | 阿里云区域（不同环境可以使用不同区域） |
| `stripe_secret_key` | Stripe密钥（dev/test使用test密钥，prod使用live密钥） |
| `stripe_publishable_key` | Stripe发布密钥（dev/test使用test密钥，prod使用live密钥） |
| `posthog_key` | PostHog密钥（可以使用相同值，但建议区分） |

## 安全注意事项

1. **密码管理**：
   - 每个环境使用不同的强密码
   - 定期轮换密码
   - 使用密码管理器存储密码

2. **版本控制**：
   - 所有 `terraform.tfvars.*` 文件已添加到 `.gitignore`
   - 不要将包含实际密码的文件提交到版本控制

3. **访问控制**：
   - 限制对 Terraform state 文件的访问
   - 使用 RAM 角色和最小权限原则
   - 生产环境部署需要额外审批

## Git管理说明

### 应该提交到Git的文件

以下文件**应该**提交到版本控制：

- ✅ 所有 `.tf` 文件（Terraform代码）
- ✅ `terraform.tfvars.example`（配置模板）
- ✅ `backend-config.{dev|test|prod}.example`（Backend配置模板）
- ✅ `backend.tf.example`（Backend配置示例）
- ✅ `README.md`（文档）
- ✅ `scripts/` 目录下的所有脚本

### 不应该提交到Git的文件

以下文件**不应该**提交到版本控制（已在 `.gitignore` 中）：

- ❌ `terraform.tfvars.dev`（包含实际密码和密钥）
- ❌ `terraform.tfvars.test`（包含实际密码和密钥）
- ❌ `terraform.tfvars.prod`（包含实际密码和密钥）
- ❌ `backend-config.dev`（包含实际配置）
- ❌ `backend-config.test`（包含实际配置）
- ❌ `backend-config.prod`（包含实际配置）
- ❌ `backend.tf`（包含实际Backend配置）
- ❌ `terraform.tfstate`（State文件）
- ❌ `terraform.tfstate.backup`（State备份文件）
- ❌ `.terraform/`（Terraform工作目录）
- ❌ `.terraform.lock.hcl`（Provider锁定文件）

### 初始化新环境

当需要为新环境初始化配置时：

1. **复制配置模板**：
   ```bash
   cp terraform.tfvars.example terraform.tfvars.{environment}
   cp backend-config.{environment}.example backend-config.{environment}
   ```

2. **编辑配置文件**：
   - 编辑 `terraform.tfvars.{environment}`，填入实际值
   - 编辑 `backend-config.{environment}`，确认区域和bucket名称

3. **初始化Backend**：
   ```bash
   cd scripts
   ./init-backend.sh {environment}
   ```

4. **初始化Terraform**：
   ```bash
   terraform init -backend-config=backend-config.{environment}
   ```

## 故障排查

### 环境变量验证失败

如果看到错误：`Environment must be one of: dev, test, prod`

检查 `terraform.tfvars.*` 文件中的 `environment` 值是否正确：
- ✅ 正确：`environment = "dev"`
- ❌ 错误：`environment = "development"` 或 `environment = "production"`

### 找不到配置文件

确保在 `deploy/aliyun/ack/terraform` 目录下运行 terraform 命令，或使用绝对路径：

```bash
terraform apply -var-file=/path/to/terraform.tfvars.dev
```

### OSS Backend初始化失败

如果 `init-backend.sh` 脚本失败：

1. 检查阿里云 CLI 是否已安装：`aliyun --version`
2. 检查是否已配置凭证：`aliyun configure get`
3. 检查是否有创建 OSS Bucket 的权限
4. 检查 bucket 名称是否已存在（OSS bucket 名称全局唯一）

## 相关文档

- [主部署文档](../../../../README.md)
- [阿里云ACK部署详细文档](../../README.md)

