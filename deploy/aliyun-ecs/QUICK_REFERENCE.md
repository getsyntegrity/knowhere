# 快速迁移参考表

## AWS → 阿里云命令对照

### Terraform资源对照

| Terraform资源 | AWS | 阿里云 | 差异 |
|--------------|-----|--------|------|
| Provider | `aws` | `alicloud` | 参数不同 |
| VPC | `aws_vpc` | `alicloud_vpc` | 几乎相同 |
| Subnet | `aws_subnet` | `alicloud_vswitch` | 名称不同 |
| 安全组 | `aws_security_group` | `alicloud_security_group` | 规则语法不同 |
| 实例 | `aws_instance` | `alicloud_instance` | 参数不同 |
| 数据库 | `aws_db_instance` | `alicloud_db_instance` | 参数不同 |
| Redis | `aws_elasticache_replication_group` | `alicloud_kvstore_instance` | 配置方式不同 |
| 对象存储 | `aws_s3_bucket` | `alicloud_oss_bucket` | API完全不同 |
| 弹性IP | `aws_eip` | `alicloud_eip` | 使用方式不同 |

### CLI命令对照

| 操作 | AWS CLI | 阿里云CLI |
|------|---------|-----------|
| 查看实例列表 | `aws ec2 describe-instances` | `aliyun ecs DescribeInstances` |
| SSH登录 | `ssh -i key.pem ubuntu@ip` | `ssh root@ip` |
| 查看日志 | `aws logs get-log-events` | 控制台或CLI |
| 存储桶操作 | `aws s3 ls` | `aliyun oss ls` |
| 上传文件 | `aws s3 cp file s3://bucket/` | `aliyun oss cp file oss://bucket/` |

### 服务端点对照

| 服务 | AWS | 阿里云 |
|------|-----|--------|
| 数据库 | `xxx.rds.amazonaws.com` | `xxx.rds.aliyuncs.com` |
| Redis | `xxx.cache.amazonaws.com` | `xxx.redis.aliyuncs.com` |
| 对象存储 | `s3.amazonaws.com` | `oss-cn-hangzhou.aliyuncs.com` |
| API网关 | `execute-api.us-east-1.amazonaws.com` | `apigateway.cn-hangzhou.aliyuncs.com` |

### 环境变量对照

| AWS | 阿里云 |
|-----|--------|
| `AWS_ACCESS_KEY_ID` | `ALICLOUD_ACCESS_KEY_ID` |
| `AWS_SECRET_ACCESS_KEY` | `ALICLOUD_SECRET_ACCESS_KEY` |
| `AWS_REGION` | `ALICLOUD_REGION` |
| `S3_BUCKET_NAME` | `OSS_BUCKET_NAME` |
| `AWS_ENDPOINT` | `OSS_ENDPOINT` |

## 关键代码调整

### Python存储代码

```python
# AWS S3
import boto3
s3_client = boto3.client('s3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)

# 上传文件
with open('file.txt', 'rb') as f:
    s3_client.upload_fileobj(f, 'bucket', 'key')

# 阿里云OSS
import oss2
auth = oss2.Auth(
    os.getenv('OSS_ACCESS_KEY_ID'),
    os.getenv('OSS_SECRET_ACCESS_KEY')
)
bucket = oss2.Bucket(auth, os.getenv('OSS_ENDPOINT'), 'bucket')

# 上传文件
bucket.put_object('key', 'file content')
```

### Node.js部署（基本不变）

```javascript
// AWS和阿里云Next.js部署方式相同
// 只需要修改环境变量
const S3_BUCKET = process.env.S3_BUCKET_NAME || process.env.OSS_BUCKET_NAME;
```

## 成本快速对比（月费用）

| 资源 | AWS | 阿里云 | 人民币 |
|------|-----|--------|--------|
| ec2.c7.large | $60 | ¥400 | ¥400 |
| RDS PostgreSQL | $15 | ¥350 | ¥350 |
| ElastiCache Redis | $15 | ¥260 | ¥260 |
| 对象存储 | $5 | ¥10 | ¥10 |
| **小计** | **$95** | **¥1020** | **~$142** |

**注意**: 
- 阿里云经常有折扣活动，实际成本可能更低
- 国内访问阿里云速度更快
- AWS需要支付流量费用

## 迁移时间估算

### 小型团队（1-2人）
- **准备阶段**: 1天
- **开发阶段**: 3天
- **测试阶段**: 2天
- **部署阶段**: 1天
- **总计**: 7天

### 中型团队（3-5人）
- **准备阶段**: 1天
- **开发阶段**: 2天
- **测试阶段**: 2天
- **部署阶段**: 1天
- **总计**: 6天

## 风险评估矩阵

| 风险项 | 可能性 | 影响 | 缓解措施 |
|--------|--------|------|---------|
| OSS API不兼容 | 高 | 中 | 使用兼容层或重写 |
| 网络延迟 | 低 | 高 | 选择合适的区域 |
| 数据迁移失败 | 低 | 高 | 充分测试，准备回滚 |
| 成本超出预算 | 中 | 低 | 预先评估和监控 |
| 服务不可用 | 低 | 高 | 配置冗余和监控 |

## 决策矩阵

### 迁移条件 ✅
- [x] 应用层代码兼容
- [x] 中间件兼容
- [x] 技术栈通用
- [x] 成本合理
- [x] 风险可控

### 不迁移条件 ❌
- [ ] 依赖AWS特定服务
- [ ] 团队无阿里云经验
- [ ] 迁移成本过高
- [ ] 风险不可控

**结论**: ✅ 条件全部满足，建议实施迁移

