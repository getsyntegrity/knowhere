#!/bin/bash

# 等待MinIO启动
echo "Waiting for MinIO to start..."
sleep 15

# 设置mc客户端
mc alias set local http://localhost:9000 minioadmin minioadmin123

# 创建bucket
echo "Creating knowhere-uploads bucket..."
mc mb local/knowhere-uploads --ignore-existing

# 启用事件通知
echo "Enabling event notification..."
mc event add local/knowhere-uploads \
  arn:minio:sqs::1:webhook \
  --event put

echo "MinIO setup completed:"
echo "- Bucket: knowhere-uploads"
echo "- Webhook: http://localhost:5005/v1/internal/s3-events"
echo "- Auth Token: dev-webhook-token"

