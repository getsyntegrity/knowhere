# OSS事件通知配置指南

本文档说明如何配置阿里云OSS的事件通知，以实现文件上传后自动触发后端任务处理。

## 概述

系统采用"预签名URL上传+事件通知"模型：
1. 前端申请上传位置（获取预签名URL）
2. 前端直接上传文件到OSS
3. OSS发送HTTP回调事件到后端
4. 后端自动触发任务处理

## OSS事件通知配置

### 方案1: 通过控制台配置（推荐用于手动操作）

#### 步骤1: 登录OSS控制台

访问：https://oss.console.aliyun.com/

#### 步骤2: 选择Bucket

选择你的存储桶（例如：`knowhere-uploads`）

#### 步骤3: 配置事件通知

1. 进入 **基础设置** → **事件通知**
2. 点击 **创建规则**
3. 配置规则：

**基本配置**:
- 规则名称: `knowhere-upload-events`
- 事件类型: 选择以下事件
  - `oss:ObjectCreated:PutObject` （普通上传）
  - `oss:ObjectCreated:PostObject` （POST上传）
  - `oss:ObjectCreated:CompleteMultipartUpload` （分片上传完成）

**过滤配置**:
- 前缀过滤: `uploads/` （只监听uploads目录下的事件）
- 后缀过滤: （可选，留空）

**回调配置**:
- 回调类型: `HTTP回调`
- 回调URL: `https://api.knowhere.ai/v1/internal/s3-events`
- 回调内容格式: `JSON`

**签名配置**:
- 回调密钥: 设置一个密钥（用于后端验证）
- 启用签名验证: ✅ （生产环境建议开启）

4. 点击 **确定** 保存配置

### 方案2: 通过API配置（推荐用于自动化）

#### 使用OSS SDK配置事件通知

```python
import oss2

# 初始化OSS客户端
auth = oss2.Auth('your-access-key-id', 'your-access-key-secret')
bucket = oss2.Bucket(auth, 'https://oss-cn-hangzhou.aliyuncs.com', 'knowhere-uploads')

# 配置事件通知规则
from oss2.models import PutBucketNotificationRequest, NotificationEventType, EventFilter

request = PutBucketNotificationRequest()
request.add_event(NotificationEventType.OBJECT_CREATED_PUT)
request.add_event(NotificationEventType.OBJECT_CREATED_POST)
request.add_event(NotificationEventType.OBJECT_CREATED_MULTIPART_UPLOAD_COMPLETE)

# 设置过滤器
event_filter = EventFilter()
event_filter.key_prefix = 'uploads/'
request.add_filter(event_filter)

# 设置回调
request.add_callback(
    callback_url='https://api.knowhere.ai/v1/internal/s3-events',
    callback_host='api.knowhere.ai',
    callback_body='{"events": [{"eventName": "${eventName}", "eventSource": "acs:oss", "eventTime": "${eventTime}", "region": "${region}", "oss": {"bucket": {"name": "${bucketName}"}, "object": {"key": "${objectName}", "size": "${objectSize}"}}}]}',
    callback_body_type='application/json'
)

# 应用配置
bucket.put_bucket_notification(request)
```

### 方案3: 通过Terraform配置（推荐用于基础设施即代码）

创建文件 `deploy/aliyun-ecs/terraform/oss-events.tf`:

```hcl
# OSS事件通知配置
resource "alicloud_oss_bucket_notification" "upload_events" {
  bucket = alicloud_oss_bucket.main.bucket

  # 配置事件通知规则
  notification {
    # 事件类型
    events = [
      "oss:ObjectCreated:PutObject",
      "oss:ObjectCreated:PostObject",
      "oss:ObjectCreated:CompleteMultipartUpload"
    ]
    
    # 过滤器
    filter_prefix = "uploads/"
    
    # HTTP回调
    callback {
      url = "https://api.knowhere.ai/v1/internal/s3-events"
      host = "api.knowhere.ai"
      body = jsonencode({
        events = [{
          eventName   = "${eventName}"
          eventSource = "acs:oss"
          eventTime   = "${eventTime}"
          region      = "${region}"
          oss = {
            bucket = {
              name = "${bucketName}"
            }
            object = {
              key  = "${objectName}"
              size = "${objectSize}"
            }
          }
        }]
      })
      body_type = "application/json"
    }
  }
}
```

然后执行：
```bash
terraform apply
```

## 后端配置

### 环境变量配置

在 `.env` 文件中添加：

```bash
# 存储类型设置为OSS
S3_TYPE=oss

# OSS基本配置
S3_BUCKET_NAME=knowhere-uploads
S3_ACCESS_KEY_ID=your-oss-access-key-id
S3_SECRET_ACCESS_KEY=your-oss-secret-access-key
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com

# OSS事件通知配置
OSS_EVENT_CALLBACK_KEY=your-callback-key  # 与OSS控制台配置的回调密钥一致
OSS_EVENT_VERIFY_SIGNATURE=true
```

### 验证配置

1. 检查OSS事件通知配置是否正确：
```bash
# 使用OSS CLI检查
aliyun oss bucket-referer get oss://knowhere-uploads
```

2. 测试事件回调：
```bash
# 上传一个测试文件
curl -X PUT "预签名URL" \
  -H "Content-Type: application/pdf" \
  --data-binary @test.pdf

# 检查后端日志，应该看到OSS事件被接收
tail -f logs/app_*.log | grep "OSS事件"
```

## OSS事件格式

OSS事件回调的标准格式：

```json
{
  "events": [
    {
      "eventName": "ObjectCreated:PutObject",
      "eventSource": "acs:oss",
      "eventTime": "2025-01-25T10:00:00.000Z",
      "region": "cn-hangzhou",
      "oss": {
        "bucket": {
          "name": "knowhere-uploads",
          "arn": "acs:oss:::knowhere-uploads"
        },
        "object": {
          "key": "uploads/job_abc123.pdf",
          "size": 1024,
          "etag": "d41d8cd98f00b204e9800998ecf8427e"
        }
      }
    }
  ]
}
```

后端会自动将此格式转换为S3Event格式，复用现有的处理逻辑。

## 安全考虑

### 签名验证

OSS HTTP回调支持签名验证，确保请求来自OSS服务：

1. **在OSS控制台配置回调密钥**
2. **在后端配置相同的密钥**（`OSS_EVENT_CALLBACK_KEY`）
3. **启用签名验证**（`OSS_EVENT_VERIFY_SIGNATURE=true`）

### IP白名单（可选）

如果后端API有IP白名单限制，需要添加OSS服务的IP段：
- 查看阿里云OSS文档获取IP段
- 在API网关或Nginx配置中添加白名单规则

### HTTPS要求

- 回调URL必须使用HTTPS
- 后端SSL证书必须有效
- 建议使用合法的SSL证书（避免OSS拒绝回调）

## 故障排查

### 问题1: 事件未触发

**检查项**:
1. ✅ OSS事件通知规则是否已创建
2. ✅ 事件类型是否包含 `ObjectCreated:PutObject`
3. ✅ 前缀过滤是否为 `uploads/`
4. ✅ 回调URL是否正确（必须是HTTPS且可访问）
5. ✅ 文件是否上传到了 `uploads/` 前缀下

**调试方法**:
```bash
# 检查OSS事件通知配置
aliyun oss bucket-notification get oss://knowhere-uploads

# 查看后端日志
tail -f logs/app_*.log | grep -i "oss\|event"
```

### 问题2: 签名验证失败

**检查项**:
1. ✅ `OSS_EVENT_CALLBACK_KEY` 是否与OSS控制台配置一致
2. ✅ `OSS_EVENT_VERIFY_SIGNATURE` 是否正确设置
3. ✅ 后端代码中的签名验证逻辑是否正确实现

**临时解决方案**:
- 开发环境可以设置 `OSS_EVENT_VERIFY_SIGNATURE=false` 跳过验证
- **生产环境必须启用签名验证**

### 问题3: 回调超时

**原因**:
- 后端处理时间过长
- 网络延迟

**解决方案**:
1. 后端立即返回200状态码
2. 异步处理事件逻辑
3. 增加OSS回调超时时间（OSS默认30秒）

### 问题4: 事件格式解析失败

**检查项**:
1. ✅ 确认OSS事件格式与代码中的模型匹配
2. ✅ 检查日志中的原始事件数据
3. ✅ 验证 `OSSEvent` schema是否正确

**调试方法**:
```python
# 在 handle_oss_event 中添加日志
logger.info(f"原始OSS事件数据: {event_data}")
logger.info(f"解析后的事件: {oss_event}")
```

## 测试方法

### 1. 功能测试

```bash
# 1. 创建任务（获取预签名URL）
curl -X POST "http://localhost:5005/v1/jobs" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "file_name": "test.pdf",
    "data_id": "test_001"
  }'

# 2. 使用返回的upload_url上传文件
curl -X PUT "<upload_url_from_response>" \
  -H "Content-Type: application/pdf" \
  --data-binary @test.pdf

# 3. 检查任务状态（应该自动变为processing）
curl -X GET "http://localhost:5005/v1/jobs/<job_id>" \
  -H "Authorization: Bearer <YOUR_API_KEY>"
```

### 2. 直接测试事件回调

```bash
# 模拟OSS事件回调
curl -X POST "http://localhost:5005/v1/internal/s3-events" \
  -H "Content-Type: application/json" \
  -H "x-oss-pub-key-url: http://example.com/key" \
  -d '{
    "events": [{
      "eventName": "ObjectCreated:PutObject",
      "eventSource": "acs:oss",
      "eventTime": "2025-01-25T10:00:00.000Z",
      "region": "cn-hangzhou",
      "oss": {
        "bucket": {"name": "knowhere-uploads"},
        "object": {"key": "uploads/job_test123.pdf", "size": 1024}
      }
    }]
  }'
```

## 监控和告警

### 监控指标

建议监控以下指标：
- OSS事件回调接收成功率
- 事件处理延迟
- 任务自动触发成功率
- 事件格式解析失败率

### 告警配置

在阿里云云监控中配置告警：
- 事件回调失败率 > 5%
- 事件处理延迟 > 10秒
- 连续失败次数 > 10

## 与S3/MinIO的对比

| 特性 | AWS S3 + SNS | MinIO | 阿里云OSS |
|------|-------------|-------|-----------|
| 事件推送方式 | SNS Topic | 直接HTTP | 直接HTTP |
| 事件格式 | SNS包装 | S3兼容 | OSS格式 |
| 签名验证 | SNS签名 | Token | OSS签名 |
| 配置复杂度 | 中 | 低 | 中 |
| 成本 | 中 | 免费 | 低 |

## 参考文档

- [阿里云OSS事件通知文档](https://help.aliyun.com/document_detail/31752.html)
- [OSS Python SDK文档](https://help.aliyun.com/document_detail/32026.html)
- [OSS事件格式说明](https://help.aliyun.com/document_detail/62923.html)

---

**注意事项**:
- OSS事件通知需要OSS服务主动回调，确保后端API可公网访问
- 回调URL必须使用HTTPS
- 生产环境必须启用签名验证

