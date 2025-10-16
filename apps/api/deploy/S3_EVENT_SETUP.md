# S3事件通知配置指南

本文档说明如何配置AWS S3和MinIO的事件通知，以支持文件上传后的自动任务触发。

## 概述

系统采用"萝卜坑"模型：
1. 前端申请上传位置（获取预签名URL）
2. 前端直接上传文件到S3/MinIO
3. S3/MinIO发送事件通知到后端
4. 后端自动触发任务处理

## AWS S3 + SNS配置

### 1. 创建SNS Topic

```bash
# 创建SNS Topic
aws sns create-topic --name knowhere-s3-upload-events

# 获取Topic ARN（用于后续配置）
aws sns list-topics --query 'Topics[?contains(TopicArn, `knowhere-s3-upload-events`)].TopicArn' --output text
```

### 2. 订阅Webhook Endpoint

```bash
# 订阅到webhook endpoint
aws sns subscribe \
  --topic-arn arn:aws:sns:us-west-1:YOUR_ACCOUNT_ID:knowhere-s3-upload-events \
  --protocol https \
  --notification-endpoint https://api.knowhere.ai/v1/internal/s3-events
```

### 3. 配置S3事件通知

创建 `s3-notification.json` 文件：

```json
{
  "TopicConfigurations": [
    {
      "Id": "knowhere-upload-events",
      "TopicArn": "arn:aws:sns:us-west-1:YOUR_ACCOUNT_ID:knowhere-s3-upload-events",
      "Events": [
        "s3:ObjectCreated:Put",
        "s3:ObjectCreated:Post",
        "s3:ObjectCreated:CompleteMultipartUpload"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "uploads/"
            }
          ]
        }
      }
    }
  ]
}
```

应用配置：

```bash
aws s3api put-bucket-notification-configuration \
  --bucket knowhere-uploads \
  --notification-configuration file://s3-notification.json
```

### 4. 验证配置

```bash
# 检查S3事件通知配置
aws s3api get-bucket-notification-configuration --bucket knowhere-uploads

# 检查SNS订阅
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-west-1:YOUR_ACCOUNT_ID:knowhere-s3-upload-events
```

## MinIO配置

### 1. 配置Webhook

```bash
# 设置webhook配置
mc admin config set local notify_webhook:1 \
  endpoint="http://api:8000/v1/internal/s3-events" \
  auth_token="your-secret-token" \
  queue_limit="100" \
  comment="Knowhere S3 upload events"

# 重启MinIO使配置生效
mc admin service restart local
```

### 2. 启用事件通知

```bash
# 为特定bucket启用事件通知
mc event add local/knowhere-uploads \
  arn:minio:sqs::1:webhook \
  --event put

# 验证事件配置
mc event list local/knowhere-uploads
```

### 3. 环境变量配置

在 `.env` 文件中添加：

```bash
# MinIO webhook认证token
S3_WEBHOOK_AUTH_TOKEN=your-secret-token

# 是否验证SNS签名（生产环境建议开启）
SNS_SIGNATURE_VERIFICATION=true
```

## 本地开发配置

### 1. 使用Docker Compose（推荐）

使用 `docker-compose.dev.yml` 配置，MinIO使用宿主机网络模式：

```bash
# 启动所有服务
cd apps/api/deploy
docker-compose -f docker-compose.dev.yml up -d

# 等待服务启动后，运行初始化脚本
docker exec knowhere_minio /docker-entrypoint-initdb.d/setup-webhook.sh
```

**关键配置**：
- MinIO使用 `network_mode: host`，可以直接访问 `localhost:8000`
- Webhook endpoint: `http://localhost:8000/v1/internal/s3-events`
- 认证token: `dev-webhook-token`

### 2. 手动配置MinIO

```bash
# 启动MinIO
docker run -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=admin \
  -e MINIO_ROOT_PASSWORD=password123 \
  minio/minio server /data --console-address ":9001"

# 配置mc客户端
mc alias set local http://localhost:9000 admin password123

# 创建bucket
mc mb local/knowhere-uploads

# 配置webhook（指向本地API）
mc admin config set local notify_webhook:1 \
  endpoint="http://localhost:8000/v1/internal/s3-events" \
  auth_token="dev-webhook-token"

# 启用事件
mc event add local/knowhere-uploads \
  arn:minio:sqs::1:webhook \
  --event put
```

### 3. 环境变量

```bash
# 开发环境配置
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin123
S3_BUCKET_NAME=knowhere-uploads
S3_WEBHOOK_AUTH_TOKEN=dev-webhook-token
SNS_SIGNATURE_VERIFICATION=false

# 数据库配置
DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere
REDIS_URL=redis://localhost:6379/0
```

## 测试配置

### 1. 测试文件上传流程

```bash
# 1. 创建任务（申请萝卜坑）
curl -X POST "http://localhost:8000/v1/jobs" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "file_name": "test.pdf",
    "data_id": "test_001",
    "parsing_params": {
      "kb_dir": "测试目录"
    }
  }'

# 2. 上传文件到返回的upload_url
curl -X PUT "UPLOAD_URL_FROM_RESPONSE" \
  -H "Content-Type: application/pdf" \
  --data-binary @test.pdf

# 3. 检查任务状态
curl -X GET "http://localhost:8000/v1/jobs/JOB_ID" \
  -H "Authorization: Bearer <YOUR_API_KEY>"
```

### 2. 测试Webhook

```bash
# 直接测试webhook endpoint
curl -X POST "http://localhost:8000/v1/internal/s3-events" \
  -H "Content-Type: application/json" \
  -H "x-minio-auth-token: dev-token" \
  -d '{
    "Records": [{
      "eventName": "s3:ObjectCreated:Put",
      "s3": {
        "bucket": {"name": "knowhere-uploads"},
        "object": {"key": "uploads/job_abc123.pdf"}
      }
    }]
  }'
```

## 故障排查

### 1. 检查日志

```bash
# 查看API日志
tail -f logs/app_$(date +%Y-%m-%d).log | grep -i "s3\|webhook\|upload"

# 查看MinIO日志
docker logs minio_container_name
```

### 2. 常见问题

**问题：Webhook未触发**
- 检查MinIO事件配置：`mc event list local/knowhere-uploads`
- 检查网络连通性：API能否访问MinIO
- 检查认证token是否正确

**问题：SNS签名验证失败**
- 检查SNS订阅状态
- 验证HTTPS证书有效性
- 检查请求头格式

**问题：任务状态未更新**
- 检查job_id提取逻辑
- 验证S3文件确实存在
- 检查任务处理流程

### 3. 调试模式

```bash
# 启用详细日志
export LOG_LEVEL=DEBUG

# 禁用SNS签名验证（仅开发环境）
export SNS_SIGNATURE_VERIFICATION=false
```

## 安全注意事项

1. **生产环境必须启用SNS签名验证**
2. **使用强随机token作为MinIO认证**
3. **限制webhook endpoint的访问权限**
4. **定期轮换认证凭据**
5. **监控异常事件和失败率**

## 监控和告警

建议监控以下指标：
- Webhook接收成功率
- 任务自动触发成功率
- S3事件延迟
- 失败重试次数

可以集成到现有的监控系统中，如Prometheus + Grafana。
