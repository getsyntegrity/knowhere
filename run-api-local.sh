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
  -e RABBITMQ_HOST=knowhere_rabbitmq \
  -e RABBITMQ_PORT=5672 \
  -e RABBITMQ_USER=admin \
  -e RABBITMQ_PASSWORD=admin123 \
  -e RABBITMQ_VHOST=/ \
  -e CELERY_BROKER_URL=amqp://admin:admin123@knowhere_rabbitmq:5672// \
  -e MESSAGE_BROKER_TYPE=rabbitmq \
  -e SECRET_KEY=test-secret-key-for-development-only \
  -e TMP_PATH=/tmp/aismart_bid \
  -e FONT_PATH=/usr/share/fonts \
  -e CHROMEDRIVER_PATH=/usr/bin/chromedriver \
  knowhere-backend:local
