# Terraform 配置指南 - AWS Prod 环境

> **重要说明**：Terraform 仅用于 **prod 环境（main 分支）** 的 Serverless 部署。
> 
> - **dev 环境**：不进行远程部署，仅本地开发（不使用 Terraform）
> - **test 环境**（staging 分支）：使用 EC2 + Docker Compose（不使用 Terraform）
> - **prod 环境**（main 分支）：使用 ECS Fargate Serverless（使用 Terraform）✅

## 环境配置文件

Terraform 仅用于 prod 环境，配置文件：

- `terraform.tfvars.prod` - 生产环境配置

**注意**：
- 此文件包含敏感信息（密码、密钥等），已添加到 `.gitignore`，不会提交到版本控制
- dev 和 test 环境不使用 Terraform，请参考：
  - Test 环境：使用 [EC2 + Docker Compose](../README.md) 方案
  - Dev 环境：使用 [本地开发环境](../../local-dev/README.md)

## Terraform State 管理

### 为什么需要远程 State？

`terraform.tfstate` 文件记录了 Terraform 管理的所有资源的实际状态。**强烈建议使用远程 State**，原因如下：

1. **团队协作**：State 存储在 S3，团队成员可以共享
2. **状态锁定**：DynamoDB 提供锁定机制，防止并发修改
3. **版本控制**：S3 支持版本控制，可以恢复历史状态
4. **加密存储**：State 文件自动加密，保护敏感信息

### Backend 配置（推荐）

**强烈建议使用 S3 + DynamoDB Backend**，而不是本地 state 文件：

- ✅ **远程存储**：State 存储在 S3，团队成员可以共享
- ✅ **状态锁定**：DynamoDB 提供锁定机制，防止并发修改
- ✅ **版本控制**：S3 支持版本控制，可以恢复历史状态
- ✅ **加密存储**：State 文件自动加密，保护敏感信息

### 初始化 Backend

**首次使用前，需要先创建 Backend 资源（S3 Bucket 和 DynamoDB Table）：**

```bash
# 初始化生产环境的 Backend
cd deploy/aws/terraform/scripts
./init-backend.sh prod
```

脚本会自动创建：
- S3 Bucket：`knowhere-terraform-state-prod`
- DynamoDB Table：`knowhere-terraform-locks-prod`

### 配置 Backend

1. **复制 Backend 配置文件**：

```bash
cd deploy/aws/terraform

# 生产环境
cp backend-config.prod.example backend-config.prod
# 编辑 backend-config.prod，确认区域和配置正确
```

2. **初始化 Terraform（使用 Backend）**：

```bash
# 生产环境
terraform init -backend-config=backend-config.prod
```

**注意**：
- `backend-config.prod` 文件包含环境特定的配置，已添加到 `.gitignore`
- 首次使用或更新 Backend 配置后，需要重新运行 `terraform init -backend-config=backend-config.prod`

### 本地 State（不推荐，仅用于测试）

如果暂时不想使用 Backend，可以继续使用本地 state 文件，但**强烈不推荐用于生产环境**：

```bash
# 生产环境（本地 State，不推荐）
terraform init
terraform apply -var-file=terraform.tfvars.prod
```

**⚠️ 警告**：本地 state 方式不推荐用于生产环境，因为：
- State 文件可能丢失
- 无法团队协作
- 没有状态锁定机制

## 使用方法

### 1. 初始化配置文件

首次使用时，需要复制示例文件并填入实际值：

```bash
# 生产环境
cp terraform.tfvars.example terraform.tfvars.prod
# 编辑 terraform.tfvars.prod，填入生产环境的实际值
```

### 2. 初始化 Terraform（使用 Backend）

**首次部署前，必须先初始化 Backend：**

```bash
# 生产环境
terraform init -backend-config=backend-config.prod
```

### 3. 部署生产环境

使用 `-var-file` 参数指定要使用的配置文件，并通过命令行自动获取版本号：

```bash
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
# 部署生产环境
cd ../scripts
export ENVIRONMENT=prod
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
./deploy.sh all
```

### 4. 版本号自动获取说明

版本号获取规则：
- **prod 分支（main）**：应该有 Git Tag，使用 Tag（如 `v1.0.0`）

部署脚本会自动根据当前 Git 状态获取版本号：
- 如果有精确匹配的 Tag → 使用 Tag（如 `v1.0.0`）
- 如果有 Tag 但不是精确匹配 → 使用 Tag+commit hash（如 `v1.0.0-abc1234`）
- 如果没有 Tag → 使用 `prod-commit hash`（如 `prod-abc1234`）

### 5. 配合部署脚本使用（推荐）

部署脚本会自动使用 `ENVIRONMENT=prod` 环境变量并获取版本号：

```bash
# 设置环境
export ENVIRONMENT=prod
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1

# 构建和推送镜像（会自动获取版本号）
cd ../scripts
./build-and-push.sh

# 部署基础设施（会自动获取版本号）
./deploy.sh all
```

## 环境变量说明

生产环境的配置文件需要设置以下变量：

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
| `environment` | 环境名称 | `prod` | **必须设置为 `prod`** |
| `app_version` | 应用版本号 | `prod` | **建议通过命令行自动获取，不要在此文件中设置** |
| `mq_username` | RabbitMQ用户名 | `admin` | `admin` |
| `api_webhook_endpoint` | API Webhook端点 | `""` | `https://api.knowhereto.ai/v1/internal/s3-events` |

### Secrets Manager 变量（敏感信息，建议设置）

| 变量名 | 说明 | 默认值 | 是否必需 |
|--------|------|--------|---------|
| `s3_access_key_id` | S3访问密钥ID | `""` | 是（应用需要访问S3） |
| `s3_secret_access_key` | S3秘密访问密钥 | `""` | 是（应用需要访问S3） |

**注意**：S3桶名会根据环境自动生成，格式为：`{project_name}-prod-storage-{8位随机字符串}`

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
  --secret-id "knowhere/prod/secret-name" \
  --secret-string "value" \
  --region us-east-1
```

## 生产环境配置

生产环境（prod）在资源创建时会有以下配置：

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

### 需要配置的变量

以下变量**必须**在生产环境中设置：

| 变量名 | prod环境 |
|--------|----------|
| `domain_name` | 生产域名 |
| `db_password` | 生产数据库密码 |
| `mq_password` | 生产RabbitMQ密码 |
| `api_webhook_endpoint` | `https://api.{domain}/v1/internal/s3-events` |
| `s3_access_key_id` | 生产S3密钥 |
| `s3_secret_access_key` | 生产S3密钥 |
| `app_secret_key` | 生产JWT密钥 |

以下变量**建议**设置（但可以使用默认值）：

| 变量名 | 说明 |
|--------|------|
| `aws_region` | AWS区域 |
| `stripe_secret_key` | Stripe密钥（使用live密钥） |
| `stripe_publishable_key` | Stripe发布密钥（使用live密钥） |
| `posthog_key` | PostHog密钥 |

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
- ✅ `backend-config.prod.example`（Backend配置模板）
- ✅ `backend.tf.example`（Backend配置示例）
- ✅ `README.md`（文档）
- ✅ `scripts/` 目录下的所有脚本

### 不应该提交到Git的文件

以下文件**不应该**提交到版本控制（已在 `.gitignore` 中）：

- ❌ `terraform.tfvars.prod`（包含实际密码和密钥）
- ❌ `backend-config.prod`（包含实际配置）
- ❌ `backend.tf`（包含实际Backend配置）
- ❌ `terraform.tfstate`（State文件）
- ❌ `terraform.tfstate.backup`（State备份文件）
- ❌ `.terraform/`（Terraform工作目录）
- ❌ `.terraform.lock.hcl`（Provider锁定文件）

### 初始化生产环境

当需要初始化生产环境配置时：

1. **复制配置模板**：
   ```bash
   cp terraform.tfvars.example terraform.tfvars.prod
   cp backend-config.prod.example backend-config.prod
   ```

2. **编辑配置文件**：
   - 编辑 `terraform.tfvars.prod`，填入实际值
   - 编辑 `backend-config.prod`，确认区域和bucket名称

3. **初始化Backend**：
   ```bash
   cd scripts
   ./init-backend.sh prod
   ```

4. **初始化Terraform**：
   ```bash
   terraform init -backend-config=backend-config.prod
   ```

## 故障排查

### 环境变量验证失败

如果看到错误：`Environment must be 'prod'`

**注意**：Terraform 仅用于 prod 环境，environment 变量必须设置为 "prod"。

检查 `terraform.tfvars.prod` 文件中的 `environment` 值是否正确：
- ✅ 正确：`environment = "prod"`
- ❌ 错误：`environment = "production"` 或其他值

### 其他环境部署

- **dev 环境**：不进行远程部署，仅本地开发，请参考 [本地开发环境](../../local-dev/README.md)
- **test 环境**：使用 EC2 + Docker Compose，请参考 [AWS EC2 部署文档](../README.md)

### 找不到配置文件

确保在 `deploy/aws/terraform` 目录下运行 terraform 命令，或使用绝对路径：

```bash
terraform apply -var-file=terraform.tfvars.prod
```

## 相关文档

- [主部署文档](../../README.md) - 了解整体部署方案
- [AWS 部署指南](../DEPLOYMENT_AWS.md) - AWS 平台完整部署指南
- [AWS EC2 部署文档](../README.md) - Test 环境（EC2 + Docker Compose）部署文档
- [本地开发环境](../../local-dev/README.md) - Dev 环境本地开发配置

