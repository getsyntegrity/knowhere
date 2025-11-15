# Terraform Plan 资源详细说明

本文档详细说明 dev 环境部署计划中将要创建的所有 AWS 资源及其作用。

> **注意**：本文档基于 dev 环境的部署计划生成。其他环境的资源配置可能有所不同，但资源类型和作用类似。

## 资源统计

- **总资源数**: 88 个资源将创建
- **需要替换**: 5 个资源需要替换（因为环境名称从空变为 dev）
- **需要销毁**: 5 个资源将被销毁（旧环境资源）

---

## 一、网络基础设施 (VPC & Networking) - 12个资源

### 1. VPC (虚拟私有云)
- **资源**: `aws_vpc.main`
- **作用**: 创建独立的虚拟网络环境，隔离 dev 环境的资源
- **配置**: CIDR 10.0.0.0/16，启用 DNS 支持

### 2. 子网 (Subnets)
- **资源**: 
  - `aws_subnet.public[0]` - 公共子网 1
  - `aws_subnet.public[1]` - 公共子网 2
  - `aws_subnet.private[0]` - 私有子网 1
  - `aws_subnet.private[1]` - 私有子网 2
- **作用**: 
  - **公共子网**: 用于需要直接访问互联网的资源（ALB、NAT Gateway）
  - **私有子网**: 用于内部资源（ECS、RDS、Redis），不直接暴露到互联网
- **高可用**: 分布在 2 个可用区，提供容错能力

### 3. 互联网网关 (Internet Gateway)
- **资源**: `aws_internet_gateway.main`
- **作用**: 为 VPC 提供互联网访问能力，允许公共子网中的资源访问互联网

### 4. NAT 网关 (NAT Gateway)
- **资源**: 
  - `aws_nat_gateway.main[0]` - NAT 网关 1
  - `aws_nat_gateway.main[1]` - NAT 网关 2
- **作用**: 允许私有子网中的资源（如 ECS 任务）访问互联网，同时保持私有性
- **高可用**: 每个可用区一个，确保高可用性

### 5. 弹性 IP (Elastic IP)
- **资源**: 
  - `aws_eip.nat[0]` - NAT 网关 1 的弹性 IP
  - `aws_eip.nat[1]` - NAT 网关 2 的弹性 IP
- **作用**: 为 NAT 网关提供静态公网 IP 地址

### 6. 路由表 (Route Tables)
- **资源**: 
  - `aws_route_table.public` - 公共路由表
  - `aws_route_table.private[0]` - 私有路由表 1
  - `aws_route_table.private[1]` - 私有路由表 2
- **作用**: 定义网络流量路由规则
  - **公共路由表**: 路由到互联网网关
  - **私有路由表**: 路由到 NAT 网关

### 7. 路由表关联 (Route Table Associations)
- **资源**: 
  - `aws_route_table_association.public[0]` - 公共子网 1 关联
  - `aws_route_table_association.public[1]` - 公共子网 2 关联
  - `aws_route_table_association.private[0]` - 私有子网 1 关联
  - `aws_route_table_association.private[1]` - 私有子网 2 关联
- **作用**: 将子网与路由表关联，使路由规则生效

---

## 二、安全组 (Security Groups) - 6个资源

安全组是虚拟防火墙，控制资源的入站和出站流量。

### 1. ALB 安全组
- **资源**: `aws_security_group.alb`
- **作用**: 控制负载均衡器的流量
- **规则**: 允许 HTTPS (443) 和 HTTP (80) 入站流量

### 2. ECS 任务安全组
- **资源**: `aws_security_group.ecs_tasks`
- **作用**: 控制 ECS 容器任务的网络访问
- **规则**: 仅允许来自 ALB 的流量

### 3. RDS 安全组
- **资源**: `aws_security_group.rds`
- **作用**: 保护数据库访问
- **规则**: 仅允许来自 ECS 任务的数据库连接（端口 5432）

### 4. ElastiCache 安全组
- **资源**: `aws_security_group.elasticache`
- **作用**: 保护 Redis 缓存访问
- **规则**: 仅允许来自 ECS 任务的 Redis 连接（端口 6379）

### 5. MQ 安全组
- **资源**: `aws_security_group.mq`
- **作用**: 保护 RabbitMQ 消息队列访问
- **规则**: 
  - AMQP over TLS (端口 5671)
  - RabbitMQ 管理界面 (端口 15671)

### 6. EFS 安全组
- **资源**: `aws_security_group.efs`
- **作用**: 保护 EFS 文件系统访问
- **规则**: 允许来自 ECS 任务的 NFS 访问（端口 2049）

---

## 三、容器服务 (ECS & ECR) - 9个资源

### 1. ECR 仓库 (容器镜像存储)
- **资源**: 
  - `aws_ecr_repository.backend` - 后端服务镜像仓库
  - `aws_ecr_repository.frontend` - 前端服务镜像仓库
  - `aws_ecr_repository.worker` - Worker 服务镜像仓库
- **作用**: 存储 Docker 镜像，供 ECS 服务拉取使用

### 2. ECR 生命周期策略
- **资源**: 
  - `aws_ecr_lifecycle_policy.backend`
  - `aws_ecr_lifecycle_policy.frontend`
  - `aws_ecr_lifecycle_policy.worker`
- **作用**: 自动清理旧镜像，保留最近 10 个镜像，节省存储成本

### 3. ECS 任务定义 (Task Definitions)
- **资源**: 
  - `aws_ecs_task_definition.backend` - 后端任务定义
  - `aws_ecs_task_definition.frontend` - 前端任务定义
  - `aws_ecs_task_definition.worker` - Worker 任务定义
- **作用**: 定义容器运行配置
  - **CPU/内存**: 后端和 Worker 各 1 vCPU/2GB，前端 0.5 vCPU/1GB
  - **环境变量**: 从 Secrets Manager 获取敏感信息
  - **日志**: 发送到 CloudWatch Logs
  - **存储**: Worker 挂载 EFS 用于模型缓存

---

## 四、数据库 (RDS) - 3个资源

### 1. RDS 子网组
- **资源**: `aws_db_subnet_group.main`
- **作用**: 定义 RDS 数据库可以部署的子网范围（私有子网）

### 2. RDS 集群 (Aurora PostgreSQL Serverless v2)
- **资源**: `aws_rds_cluster.postgres`
- **作用**: 创建 PostgreSQL 数据库集群
- **特性**: 
  - Serverless v2，自动扩缩容（0.5-16 ACU）
  - 多可用区部署
  - 自动备份
  - 加密存储

### 3. RDS 实例
- **资源**: `aws_rds_cluster_instance.postgres[0]`
- **作用**: 数据库集群的实例节点
- **配置**: dev 环境使用单实例

---

## 五、缓存 (ElastiCache Redis) - 2个资源

### 1. ElastiCache 子网组
- **资源**: `aws_elasticache_subnet_group.main`
- **作用**: 定义 Redis 可以部署的子网范围

### 2. ElastiCache Serverless Cache
- **资源**: `aws_elasticache_serverless_cache.redis`
- **作用**: 创建 Serverless Redis 缓存
- **特性**: 
  - 自动扩缩容
  - 按使用量计费
  - 高可用性
  - 自动备份（每天 03:00）

---

## 六、消息队列 (Amazon MQ) - 1个资源

### 1. RabbitMQ Broker
- **资源**: `aws_mq_broker.rabbitmq`
- **作用**: 创建完全托管的 RabbitMQ 消息队列服务
- **配置**: 
  - dev 环境: 单实例，mq.t3.micro
  - 端口: 5671 (AMQPS over TLS)
  - 管理端口: 15671
- **用途**: 处理异步任务、任务队列、事件驱动架构

---

## 七、存储 (S3 & EFS) - 5个资源

### 1. S3 存储桶
- **资源**: `aws_s3_bucket.main`
- **作用**: 对象存储，用于存储用户上传的文件
- **特性**: 
  - 版本控制
  - 加密存储
  - 阻止公共访问
  - 生命周期管理（30 天后清理旧版本）

### 2. S3 事件通知
- **资源**: `aws_s3_bucket_notification.main`
- **作用**: 当文件上传到 `uploads/` 前缀时，自动发送事件到 SNS
- **用途**: 触发文件处理流程

### 3. EFS 文件系统 (模型缓存)
- **资源**: `aws_efs_file_system.model_cache`
- **作用**: 网络文件系统，用于 Worker 服务缓存 AI 模型
- **优势**: 
  - 多个 Worker 实例共享模型缓存
  - 避免重复下载模型
  - 持久化存储

### 4. EFS 挂载目标
- **资源**: 
  - `aws_efs_mount_target.model_cache[0]` - 可用区 1
  - `aws_efs_mount_target.model_cache[1]` - 可用区 2
- **作用**: 在每个可用区创建挂载点，使 ECS 任务可以挂载文件系统

---

## 八、负载均衡 (ALB) - 已存在

**注意**: ALB 资源在现有 state 中已存在，本次不会创建新资源。

---

## 九、SSL/TLS 证书 (ACM) - 1个资源

### 1. ACM 证书
- **资源**: `aws_acm_certificate.main`
- **作用**: SSL/TLS 证书，用于 HTTPS 访问
- **域名**: `apitest.knowhereto.com`
- **用途**: ALB 使用此证书提供 HTTPS 服务

---

## 十、密钥管理 (KMS) - 4个资源

### 1. KMS 密钥 (RDS)
- **资源**: `aws_kms_key.rds`
- **作用**: 用于加密 RDS 数据库存储
- **别名**: `alias/knowhere-rds`

### 2. KMS 密钥 (Secrets Manager)
- **资源**: `aws_kms_key.secrets`
- **作用**: 用于加密 Secrets Manager 中的敏感信息
- **别名**: `alias/knowhere-secrets`

### 3. KMS 别名
- **资源**: 
  - `aws_kms_alias.rds`
  - `aws_kms_alias.secrets`
- **作用**: 为 KMS 密钥提供友好的别名，便于引用和管理

---

## 十一、密钥存储 (Secrets Manager) - 22个资源

Secrets Manager 用于安全存储敏感信息，如密码、API 密钥等。

### Secrets (11个)
- `aws_secretsmanager_secret.database_url` - 数据库连接 URL
- `aws_secretsmanager_secret.redis_host` - Redis 主机地址
- `aws_secretsmanager_secret.redis_port` - Redis 端口
- `aws_secretsmanager_secret.redis_password` - Redis 密码
- `aws_secretsmanager_secret.rabbitmq_host` - RabbitMQ 主机地址
- `aws_secretsmanager_secret.rabbitmq_username` - RabbitMQ 用户名
- `aws_secretsmanager_secret.rabbitmq_password` - RabbitMQ 密码
- `aws_secretsmanager_secret.s3_access_key` - S3 访问密钥 ID
- `aws_secretsmanager_secret.s3_secret_key` - S3 秘密访问密钥
- `aws_secretsmanager_secret.secret_key` - 应用 JWT 密钥
- `aws_secretsmanager_secret.stripe_secret_key` - Stripe 密钥（可选）
- `aws_secretsmanager_secret.stripe_publishable_key` - Stripe 发布密钥（可选）
- `aws_secretsmanager_secret.posthog_key` - PostHog 分析密钥（可选）

### Secret Versions (11个)
每个 Secret 对应一个 Version，存储实际的值。

**作用**: 
- 安全存储敏感信息
- 自动加密（使用 KMS）
- ECS 任务自动获取，无需硬编码
- 支持密钥轮换

---

## 十二、消息通知 (SNS) - 3个资源

### 1. SNS Topic
- **资源**: `aws_sns_topic.s3_events`
- **作用**: 接收 S3 事件通知

### 2. SNS Topic Policy
- **资源**: `aws_sns_topic_policy.s3_events`
- **作用**: 允许 S3 向 SNS Topic 发布消息

### 3. SNS Topic Subscription
- **资源**: `aws_sns_topic_subscription.s3_events_webhook`
- **作用**: 订阅 SNS Topic，当 S3 事件发生时，发送 HTTP POST 请求到 API webhook
- **端点**: `https://apidev.knowhereto.com/v1/internal/s3-events`

---

## 十三、访问控制 (IAM) - 6个资源

### 1. IAM 角色
- **资源**: 
  - `aws_iam_role.ecs_task_execution_role` - ECS 任务执行角色
  - `aws_iam_role.ecs_task_role` - ECS 任务角色
- **作用**: 
  - **执行角色**: 允许 ECS 拉取镜像、写入日志、访问 Secrets Manager
  - **任务角色**: 允许应用访问 S3、EFS 等资源

### 2. IAM 策略
- **资源**: 
  - `aws_iam_policy.s3_access` - S3 访问策略
  - `aws_iam_policy.efs_access` - EFS 访问策略
  - `aws_iam_role_policy.secrets_manager_access` - Secrets Manager 访问策略
- **作用**: 定义具体的权限规则

### 3. IAM 策略附件
- **资源**: 
  - `aws_iam_role_policy_attachment.ecs_task_execution_role_policy` - 基础执行策略
  - `aws_iam_role_policy_attachment.ecs_task_execution_role_efs` - EFS 访问
  - `aws_iam_role_policy_attachment.ecs_task_role_s3` - S3 访问
- **作用**: 将策略附加到角色，使权限生效

---

## 十四、日志 (CloudWatch Logs) - 3个资源

### 1. CloudWatch Log Groups
- **资源**: 
  - `aws_cloudwatch_log_group.backend` - 后端服务日志
  - `aws_cloudwatch_log_group.frontend` - 前端服务日志
  - `aws_cloudwatch_log_group.worker` - Worker 服务日志
- **作用**: 
  - 集中收集容器日志
  - 日志保留 7 天（dev 环境）
  - 支持日志查询和分析

---

## 资源依赖关系

```
VPC
  ├── Subnets (Public/Private)
  ├── Internet Gateway
  ├── NAT Gateways
  └── Route Tables
       │
       ├── ALB (负载均衡器)
       │    └── ECS Services
       │         ├── Backend (从 Secrets Manager 获取配置)
       │         ├── Frontend
       │         └── Worker (挂载 EFS)
       │
       ├── RDS (数据库)
       │    └── 使用 Secrets Manager 存储连接信息
       │
       ├── ElastiCache (Redis)
       │    └── 使用 Secrets Manager 存储连接信息
       │
       ├── Amazon MQ (RabbitMQ)
       │    └── 使用 Secrets Manager 存储连接信息
       │
       └── S3 (对象存储)
            └── SNS (事件通知)
                 └── API Webhook
```

---

## 成本估算（dev 环境）

### 主要成本项：
1. **NAT Gateway**: ~$32/月（每个可用区 $16/月）
2. **RDS Serverless v2**: 按使用量计费，约 $50-100/月
3. **ElastiCache Serverless**: 按使用量计费，约 $20-50/月
4. **Amazon MQ**: mq.t3.micro 约 $10/月
5. **ECS Fargate**: 按运行时间计费，约 $30-50/月
6. **EFS**: 按存储量计费，约 $3-10/月
7. **ALB**: 约 $16/月
8. **数据传输**: 按实际使用量

**预估总成本**: 约 $150-250/月（dev 环境）

---

## 部署后验证清单

部署完成后，请验证以下内容：

- [ ] VPC 和子网创建成功
- [ ] RDS 数据库可以连接
- [ ] Redis 缓存可以连接
- [ ] RabbitMQ 可以连接
- [ ] S3 存储桶可以访问
- [ ] EFS 文件系统可以挂载
- [ ] ECS 服务正常运行
- [ ] ALB 健康检查通过
- [ ] HTTPS 证书有效
- [ ] Secrets Manager 中的密钥可以访问
- [ ] CloudWatch Logs 有日志输出
- [ ] S3 事件通知正常工作

---

## 注意事项

1. **首次部署**: 某些资源（如 RDS、MQ）创建需要 10-20 分钟
2. **DNS 验证**: ACM 证书需要 DNS 验证，可能需要额外配置
3. **Secrets**: 确保所有 Secrets 的值都已正确设置
4. **成本**: dev 环境建议在非工作时间停止 ECS 服务以节省成本
5. **备份**: RDS 和 ElastiCache 已配置自动备份

