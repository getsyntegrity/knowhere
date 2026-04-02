#!/bin/bash

# 启动开发环境脚本
echo "🚀 启动Knowhere开发环境..."

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

# 进入部署目录
cd "$(dirname "$0")"

# 启动Docker服务
echo "📦 启动Docker服务..."
docker-compose -f docker-compose.dev.yml up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 运行LocakStack初始化脚本 (自动运行)
echo "🔧 LocalStack初始化中..."

# 检查服务状态
echo "🔍 检查服务状态..."
echo "PostgreSQL: $(docker exec knowhere_postgres pg_isready -U root -d Knowhere 2>/dev/null && echo '✅ 运行中' || echo '❌ 未运行')"
echo "Redis: $(docker exec knowhere_redis redis-cli ping 2>/dev/null && echo '✅ 运行中' || echo '❌ 未运行')"
echo "LocalStack: $(curl -s http://localhost:4566/_localstack/health > /dev/null && echo '✅ 运行中' || echo '❌ 未运行')"

echo ""
echo "🎉 开发环境启动完成！"
echo ""
echo "📋 服务访问地址："
echo "  - LocalStack: http://localhost:4566"
echo "  - PostgreSQL: localhost:5432 (root/root123)"
echo "  - Redis: localhost:6379"
echo ""
echo "🔧 下一步："
echo "  1. 启动API服务: cd apps/api && uv run python main.py"
echo "  2. 测试webhook: curl -X POST http://localhost:5005/v1/internal/s3-events \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -H 'x-minio-auth-token: dev-webhook-token' \\"
echo "     -d '{\"Records\":[{\"eventName\":\"s3:ObjectCreated:Put\",\"s3\":{\"bucket\":{\"name\":\"knowhere-uploads\"},\"object\":{\"key\":\"uploads/job_test123.pdf\"}}}]}'"
echo ""
echo "🛑 停止服务: docker-compose -f docker-compose.dev.yml down"
