# Terraform 多环境配置指南

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

**强烈建议使用 S3 + DynamoDB Backend**，而不是本地 state 文件：

- ✅ **远程存储**：State 存储在 S3，团队成员可以共享
- ✅ **状态锁定**：DynamoDB 提供锁定机制，防止并发修改
- ✅ **版本控制**：S3 支持版本控制，可以恢复历史状态
- ✅ **加密存储**：State 文件自动加密，保护敏感信息

### 初始化 Backend

**首次使用前，需要先创建 Backend 资源（S3 Bucket 和 DynamoDB Table）：**

```bash
# 初始化开发环境的 Backend
cd deploy/aws/terraform/scripts
./init-backend.sh dev

# 初始化测试环境的 Backend
./init-backend.sh test

# 初始化生产环境的 Backend
./init-backend.sh prod
```

脚本会自动创建：
- S3 Bucket：`knowhere-terraform-state-{environment}`
- DynamoDB Table：`knowhere-terraform-locks-{environment}`

### 配置 Backend

1. **复制 Backend 配置文件**：

```bash
cd deploy/aws/terraform

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
- 或者使用 `terraform workspace` 来管理多环境（但 Backend 方式更推荐）

### 本地 State（不推荐，仅用于测试）

如果暂时不想使用 Backend，可以继续使用本地 state 文件，但**必须为每个环境使用不同的工作目录**：

```bash
# 开发环境
mkdir -p terraform-dev && cd terraform-dev
cp -r ../*.tf .
terraform init
terraform apply -var-file=../terraform.tfvars.dev

# 测试环境
mkdir -p terraform-test && cd terraform-test
cp -r ../*.tf .
terraform init
terraform apply -var-file=../terraform.tfvars.test
```

**⚠️ 警告**：本地 state 方式不推荐用于生产环境，因为：
- State 文件可能丢失
- 无法团队协作
- 没有状态锁定机制

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
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
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

### 5. 配合部署脚本使用（推荐）

部署脚本会自动使用 `ENVIRONMENT` 环境变量并获取版本号：

```bash
# 设置环境
export ENVIRONMENT=dev
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1

# 构建和推送镜像（会自动获取版本号）
cd ../scripts
./build-and-push.sh

# 部署基础设施（会自动获取版本号）
./deploy.sh all
```

## 环境变量说明

每个环境的配置文件需要设置以下变量：

### 必需变量（无默认值，必须设置）

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `domain_name` | 域名 | `knowhereto.ai` |
| `db_password` | 数据库密码 | 强密码字符串 |
| `mq_password` | RabbitMQ密码 | 强密码字符串 |

### 基础配置变量（有默认值，但建议明确设置）

| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| `aws_region` | AWS区域 | `us-east-1` | `us-east-1` |
| `project_name` | 项目名称 | `knowhere` | `knowhere` |
| `environment` | 环境名称 | `dev` | `dev` / `test` / `prod` |
| `app_version` | 应用版本号 | `dev` | **建议通过命令行自动获取，不要在此文件中设置** |
| `mq_username` | RabbitMQ用户名 | `admin` | `admin` |
| `api_webhook_endpoint` | API Webhook端点 | `""` | `https://dev-api.knowhereto.ai/v1/internal/s3-events` |

### Secrets Manager 变量（敏感信息，建议设置）

| 变量名 | 说明 | 默认值 | 是否必需 |
|--------|------|--------|---------|
| `s3_access_key_id` | S3访问密钥ID | `""` | 是（应用需要访问S3） |
| `s3_secret_access_key` | S3秘密访问密钥 | `""` | 是（应用需要访问S3） |

**注意**：S3桶名会根据环境自动生成，格式为：`{project_name}-{environment}-storage-{8位随机字符串}`

- dev环境：`knowhere-dev-storage-xxxxxxxx`
- test环境：`knowhere-test-storage-xxxxxxxx`
- prod环境：`knowhere-prod-storage-xxxxxxxx`

部署后可通过以下命令查看实际桶名：
```bash
terraform output s3_bucket_name
```
| `app_secret_key` | 应用JWT密钥 | `""` | 是（用于token签名） |
| `stripe_secret_key` | Stripe密钥 | `""` | 否（支付功能需要） |
| `stripe_publishable_key` | Stripe发布密钥 | `""` | 否（支付功能需要） |
| `posthog_key` | PostHog密钥 | `""` | 否（分析功能需要） |

**注意**：如果 Secrets Manager 变量留空，secret 会被创建但值为空，需要后续手动设置：
```bash
aws secretsmanager update-secret \
  --secret-id "knowhere/{environment}/secret-name" \
  --secret-string "value" \
  --region us-east-1
```

## 环境差异

不同环境在资源创建时会有以下差异：

### 开发环境 (dev)
- **域名**：`apidev.{domain_name}`, `dev.{domain_name}`（详细配置参考 [域名配置说明](../../DOMAIN_CONFIG.md)）
- **API Webhook端点**：`https://apidev.{domain_name}/v1/internal/s3-events`
- **ECS服务实例数**：1
- **RDS实例数**：1
- **RabbitMQ**：单实例，`mq.t3.micro`，`SINGLE_INSTANCE`模式
- **日志保留**：7天
- **删除保护**：关闭（RDS、ALB）
- **S3桶名**：`knowhere-dev-storage-xxxxxxxx`（自动生成）
- **SNS Topic**：`knowhere-dev-s3-events`（自动生成）
- **EFS文件系统**：`knowhere-dev-model-cache`（自动生成）

### 测试环境 (test)
- **域名**：`apitest.{domain_name}`, `test.{domain_name}`（详细配置参考 [域名配置说明](../../DOMAIN_CONFIG.md)）
- **API Webhook端点**：`https://apitest.{domain_name}/v1/internal/s3-events`
- **ECS服务实例数**：1
- **RDS实例数**：1
- **RabbitMQ**：单实例，`mq.t3.micro`，`SINGLE_INSTANCE`模式
- **日志保留**：7天
- **删除保护**：关闭（RDS、ALB）
- **S3桶名**：`knowhere-test-storage-xxxxxxxx`（自动生成）
- **SNS Topic**：`knowhere-test-s3-events`（自动生成）
- **EFS文件系统**：`knowhere-test-model-cache`（自动生成）

### 生产环境 (prod)
- **域名**：`api.{domain_name}`, `{domain_name}`（根据domain_name变量）
- **API Webhook端点**：`https://api.{domain_name}/v1/internal/s3-events`
- **ECS服务实例数**：2（高可用）
- **RDS实例数**：2（高可用）
- **RabbitMQ**：多AZ高可用，`mq.m5.large`，`ACTIVE_STANDBY_MULTI_AZ`模式
- **日志保留**：30天
- **删除保护**：开启（RDS、ALB）
- **S3桶名**：`knowhere-prod-storage-xxxxxxxx`（自动生成）
- **SNS Topic**：`knowhere-prod-s3-events`（自动生成）
- **EFS文件系统**：`knowhere-prod-model-cache`（自动生成）

### 根据环境需要配置的变量

以下变量**必须**在不同环境中设置不同的值：

| 变量名 | dev环境 | test环境 | prod环境 |
|--------|---------|----------|----------|
| `domain_name` | 开发域名 | 测试域名 | 生产域名 |
| `db_password` | 开发数据库密码 | 测试数据库密码 | 生产数据库密码 |
| `mq_password` | 开发RabbitMQ密码 | 测试RabbitMQ密码 | 生产RabbitMQ密码 |
| `api_webhook_endpoint` | `https://apidev.{domain}/v1/internal/s3-events` | `https://apitest.{domain}/v1/internal/s3-events` | `https://api.{domain}/v1/internal/s3-events` |
| `s3_access_key_id` | 开发S3密钥 | 测试S3密钥 | 生产S3密钥 |
| `s3_secret_access_key` | 开发S3密钥 | 测试S3密钥 | 生产S3密钥 |
| `app_secret_key` | 开发JWT密钥 | 测试JWT密钥 | 生产JWT密钥 |

以下变量**建议**在不同环境中设置不同的值（但可以使用相同值）：

| 变量名 | 说明 |
|--------|------|
| `aws_region` | AWS区域（不同环境可以使用不同区域） |
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
   - 使用 IAM 角色和最小权限原则
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

确保在 `deploy/aws/terraform` 目录下运行 terraform 命令，或使用绝对路径：

```bash
terraform apply -var-file=/path/to/terraform.tfvars.dev
```

## 相关文档

- [主部署文档](../../README.md)
- [AWS部署详细文档](../README.md)

