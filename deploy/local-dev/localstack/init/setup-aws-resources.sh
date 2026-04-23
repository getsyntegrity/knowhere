#!/bin/bash

# Initialize LocalStack AWS resources after the container becomes ready.

set -e

echo "Starting LocalStack AWS resource initialization..."

# Wait until LocalStack is ready to accept requests.
echo "Waiting for LocalStack to become ready..."
sleep 10

# Point the AWS CLI at LocalStack.
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-west-1
export AWS_ENDPOINT_URL=http://localhost:4566

# Create the buckets used by local development.
echo "Creating S3 buckets..."
aws --endpoint-url=http://localhost:4566 s3 mb s3://knowhere-dev
aws --endpoint-url=http://localhost:4566 s3 mb s3://knowhere-uploads
aws --endpoint-url=http://localhost:4566 s3 mb s3://knowhere-results

# Configure bucket CORS for local browser-based development.
echo "Configuring bucket CORS..."
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

# Create the SNS topic used for upload notifications.
echo "Creating SNS topic..."
TOPIC_ARN=$(aws --endpoint-url=http://localhost:4566 sns create-topic \
  --name knowhere-s3-upload-events \
  --query 'TopicArn' --output text)

echo "SNS topic ARN: $TOPIC_ARN"

# Configure S3 event notifications.
echo "Configuring S3 event notifications..."
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

# Show the resulting LocalStack state.
echo "Verifying LocalStack resources..."
aws --endpoint-url=http://localhost:4566 s3 ls
aws --endpoint-url=http://localhost:4566 sns list-topics
aws --endpoint-url=http://localhost:4566 s3api get-bucket-notification-configuration --bucket knowhere-uploads

# Subscribe the SNS topic to the local webhook endpoint.
# NOTE: The API server runs on the host (WSL2), so use host.docker.internal
# to reach it from inside the container.
echo "Waiting for the API before subscribing SNS to the webhook..."
ATTEMPT=0
while true; do
  ATTEMPT=$((ATTEMPT + 1))
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://host.docker.internal:5005/health 2>&1) || true
  if [ "$HTTP_CODE" = "200" ]; then
    echo "API is ready (attempt #$ATTEMPT)"
    break
  fi
  echo "[attempt #$ATTEMPT] API not ready yet - http_code=$HTTP_CODE, retrying in 2s..."
  sleep 2
done

aws --endpoint-url=http://localhost:4566 sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol http \
  --notification-endpoint http://host.docker.internal:5005/v1/internal/s3-events
echo "SNS subscription created."

echo "LocalStack AWS resource initialization completed."
echo ""
echo "Service endpoints:"
echo "  - S3 endpoint: http://localhost:4566"
echo "  - SNS endpoint: http://localhost:4566"
echo "  - LocalStack health: http://localhost:4566/_localstack/health"
echo ""
echo "Suggested local environment values:"
echo "  S3_ENDPOINT_URL=http://localhost:4566"
echo "  S3_ACCESS_KEY_ID=test"
echo "  S3_SECRET_ACCESS_KEY=test"
echo "  S3_BUCKET_NAME=knowhere-uploads"
echo "  S3_UPLOADS_BUCKET=knowhere-uploads"
echo "  S3_RESULTS_BUCKET=knowhere-results"
echo "  S3_REGION=us-west-1"
echo "  S3_USE_SSL=false"
echo "  S3_ADDRESSING_STYLE=path"

```bash
curl http://localhost:5005/health
```

If the API is healthy, you can also open:

- `http://localhost:5005/docs` for the local OpenAPI docs
- `http://localhost:4566/_localstack/health` for LocalStack health

## 5. Stop Local Infrastructure

```bash
cd deploy/local-dev
./stop-dev.sh
```

That start and stop flow is the documented public local baseline. Anything more
complex should build on top of these helpers instead of replacing them.
