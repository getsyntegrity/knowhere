#!/bin/bash
# 本地运行 API 服务的脚本

docker run --rm -p 5005:5005 \
  --network deploy_knowhere_network \
  -e ENVIRONMENT=development \
  -e DS_KEY=test-key \
  -e DS_URL=https://api.deepseek.com/v1/chat/completions \
  -e S3_BUCKET_NAME=test-bucket \
  -e S3_ACCESS_KEY_ID=test-key \
  -e S3_SECRET_ACCESS_KEY=test-secret \
  -e S3_TEMP_PATH=/tmp \
  -e USERS_DATA_PATH=/tmp/users \
  -e DATABASE_URL=postgresql+asyncpg://root:root123@knowhere_postgres:5432/Knowhere \
  -e DB_SSL_MODE=disable \
  -e REDIS_HOST=knowhere_redis \
  -e REDIS_PORT=6379 \
  -e REDIS_PASSWORD= \
  -e REDIS_DATABASE=0 \
  -e CELERY_REDIS_URL=redis://knowhere_redis:6379/0 \
  -e SECRET_KEY=test-secret-key-for-development-only \
  -e TMP_PATH=/tmp/aismart_bid \
  -e FONT_PATH=/usr/share/fonts \
  -e CHROMEDRIVER_PATH=/usr/bin/chromedriver \
  knowhere-backend:local
