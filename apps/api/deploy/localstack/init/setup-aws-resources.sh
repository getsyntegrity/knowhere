#!/bin/bash

# LocalStack AWS资源初始化脚本
# 此脚本在LocalStack启动后自动执行

set -e

echo "🚀 开始初始化LocalStack AWS资源..."

# 等待LocalStack完全启动
echo "⏳ 等待LocalStack服务启动..."
sleep 10

# 设置AWS CLI配置（指向LocalStack）
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-west-1
export AWS_ENDPOINT_URL=http://localhost:4566

# 创建S3存储桶
echo "📦 创建S3存储桶..."
aws --endpoint-url=http://localhost:4566 s3 mb s3://knowhere-dev
aws --endpoint-url=http://localhost:4566 s3 mb s3://knowhere-uploads
aws --endpoint-url=http://localhost:4566 s3 mb s3://knowhere-results

# 配置S3存储桶CORS
echo "🌐 配置S3 CORS策略..."
aws --endpoint-url=http://localhost:4566 s3api put-bucket-cors \
  --bucket knowhere-dev \
  --cors-configuration '{
    "CORSRules": [
      {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
        "AllowedOrigins": ["http://localhost:3000", "http://localhost:5005"],
        "ExposeHeaders": ["ETag", "x-amz-meta-*"],
        "MaxAgeSeconds": 3000
      }
    ]
  }'

aws --endpoint-url=http://localhost:4566 s3api put-bucket-cors \
  --bucket knowhere-uploads \
  --cors-configuration '{
    "CORSRules": [
      {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
        "AllowedOrigins": ["http://localhost:3000", "http://localhost:5005"],
        "ExposeHeaders": ["ETag", "x-amz-meta-*"],
        "MaxAgeSeconds": 3000
      }
    ]
  }'

# 创建SNS主题
echo "📢 创建SNS主题..."
TOPIC_ARN=$(aws --endpoint-url=http://localhost:4566 sns create-topic \
  --name knowhere-s3-upload-events \
  --query 'TopicArn' --output text)

echo "SNS主题ARN: $TOPIC_ARN"

# 订阅SNS主题到webhook
echo "🔗 订阅SNS到webhook..."
aws --endpoint-url=http://localhost:4566 sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol http \
  --notification-endpoint http://host.docker.internal:5005/v1/internal/s3-events

# 配置S3事件通知
echo "⚡ 配置S3事件通知..."
aws --endpoint-url=http://localhost:4566 s3api put-bucket-notification-configuration \
  --bucket knowhere-uploads \
  --notification-configuration "{
    \"TopicConfigurations\": [
      {
        \"Id\": \"knowhere-upload-events\",
        \"TopicArn\": \"$TOPIC_ARN\",
        \"Events\": [
          \"s3:ObjectCreated:Put\",
          \"s3:ObjectCreated:Post\",
          \"s3:ObjectCreated:CompleteMultipartUpload\"
        ],
        \"Filter\": {
          \"Key\": {
            \"FilterRules\": [
              {
                \"Name\": \"prefix\",
                \"Value\": \"uploads/\"
              }
            ]
          }
        }
      }
    ]
  }"

# 验证配置
echo "✅ 验证配置..."
aws --endpoint-url=http://localhost:4566 s3 ls
aws --endpoint-url=http://localhost:4566 sns list-topics
aws --endpoint-url=http://localhost:4566 s3api get-bucket-notification-configuration --bucket knowhere-uploads

echo "🎉 LocalStack AWS资源初始化完成！"
echo ""
echo "📋 服务信息："
echo "  - S3端点: http://localhost:4566"
echo "  - SNS端点: http://localhost:4566"
echo "  - 管理界面: http://localhost:4566/_localstack/health"
echo ""
echo "🔧 环境变量配置："
echo "  S3_ENDPOINT_URL=http://localhost:4566"
echo "  S3_ACCESS_KEY_ID=test"
echo "  S3_SECRET_ACCESS_KEY=test"
echo "  S3_BUCKET_NAME=knowhere-dev"
echo "  S3_REGION=us-west-1"
echo "  S3_USE_SSL=false"
echo "  S3_ADDRESSING_STYLE=path"
