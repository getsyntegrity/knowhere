# 主账号凭证配置说明

## 概述

为了处理某些需要高权限的资源（如 ACK 集群），Terraform 配置支持使用主账号凭证。当 RAM 用户权限不足时，可以使用主账号凭证来操作这些资源。

## 配置方法

### 1. 在 terraform.tfvars.dev 中添加主账号凭证

```hcl
# 阿里云凭证配置（RAM 用户）
access_key = "your-ram-user-access-key-id"
secret_key = "your-ram-user-secret-key"

# 主账号凭证（用于处理需要更高权限的资源，如 ACK 集群）
master_access_key = "your-master-account-access-key-id"  # 主账号 AccessKey ID
master_secret_key = "your-master-account-secret-key"      # 主账号 AccessKey Secret
```

### 2. 工作原理

- **默认 provider**: 使用 RAM 用户凭证，用于大部分资源的操作
- **主账号 provider** (`alicloud.master`): 使用主账号凭证，专门用于需要高权限的资源
- **自动回退**: 如果未提供主账号凭证，主账号 provider 会自动使用 RAM 用户凭证

### 3. 使用主账号 provider 的资源

当前配置中，以下资源使用主账号 provider：

- `alicloud_cs_managed_kubernetes.main` (ACK 集群)

### 4. 安全注意事项

⚠️ **重要安全提示**：

1. **主账号凭证具有完整权限**，请妥善保管
2. **不要将主账号凭证提交到版本控制**
3. **建议使用 RAM 用户进行日常操作**，仅在必要时使用主账号
4. **定期轮换 AccessKey**，提高安全性
5. **使用最小权限原则**，尽量通过配置 RAM 用户权限来解决问题

### 5. 权限问题排查

如果遇到权限问题，可以：

1. **优先方案**: 配置 RAM 用户权限，使其能够操作所需资源
2. **临时方案**: 使用主账号凭证（当前实现）
3. **长期方案**: 创建专门的 RAM 角色，授予必要权限

## 使用示例

### 导入 ACK 集群（使用主账号凭证）

```bash
cd deploy/aliyun/ack/terraform

# 设置环境变量（用于 OSS backend）
export ALICLOUD_ACCESS_KEY=$(grep "^access_key" terraform.tfvars.dev | cut -d'"' -f2)
export ALICLOUD_SECRET_KEY=$(grep "^secret_key" terraform.tfvars.dev | cut -d'"' -f2)

# 导入 ACK 集群（会自动使用主账号 provider）
terraform import -var-file=terraform.tfvars.dev \
  alicloud_cs_managed_kubernetes.main <cluster-id>
```

### 运行 Terraform 操作

```bash
# Plan（会使用相应的 provider）
terraform plan -var-file=terraform.tfvars.dev

# Apply（会使用相应的 provider）
terraform apply -var-file=terraform.tfvars.dev
```

## 配置验证

验证配置是否正确：

```bash
terraform validate
```

## 相关文件

- `variables.tf`: 定义 `master_access_key` 和 `master_secret_key` 变量
- `main.tf`: 配置主账号 provider (`alicloud.master`)
- `ack.tf`: ACK 集群资源使用主账号 provider
- `terraform.tfvars.dev`: 存储主账号凭证（已添加到 .gitignore）

## 故障排除

### 问题：主账号凭证无效

**症状**: 导入或操作 ACK 资源时出现认证错误

**解决方案**:
1. 检查 `terraform.tfvars.dev` 中的主账号凭证是否正确
2. 确认主账号 AccessKey 未被禁用
3. 验证主账号 AccessKey 是否具有必要权限

### 问题：仍然出现权限错误

**症状**: 即使使用主账号凭证，仍然出现 `Forbidden.RAM` 错误

**可能原因**:
1. 资源组级别策略限制
2. 主账号本身权限受限
3. 资源属于其他账号

**解决方案**:
1. 检查资源组策略
2. 确认资源归属
3. 联系阿里云技术支持

## 最佳实践

1. **最小权限原则**: 尽量使用 RAM 用户，仅在必要时使用主账号
2. **凭证分离**: 将主账号凭证单独管理，不要与 RAM 用户凭证混用
3. **定期审查**: 定期检查哪些资源使用了主账号凭证，评估是否可以改用 RAM 用户
4. **文档记录**: 记录使用主账号凭证的原因和资源
5. **监控告警**: 对主账号凭证的使用进行监控和告警

