#!/bin/bash

# Wait for MinIO to start.
echo "Waiting for MinIO to start..."
sleep 15

# Configure the mc client.
mc alias set local http://localhost:9000 minioadmin minioadmin123

# Create the upload bucket.
echo "Creating knowhere-uploads bucket..."
mc mb local/knowhere-uploads --ignore-existing

# Enable event notifications.
echo "Enabling event notification..."
mc event add local/knowhere-uploads \
  arn:minio:sqs::1:webhook \
  --event put

echo "MinIO setup completed:"
echo "- Bucket: knowhere-uploads"
echo "- Webhook: http://localhost:5005/v1/internal/s3-events"
echo "- Auth Token: dev-webhook-token"
