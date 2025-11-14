#!/bin/bash

# 完整部署测试脚本

set -e

cd "$(dirname "$0")"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Knowhere API 完整部署测试 ===${NC}"
echo ""

# 1. 检查Docker和Docker Compose
echo -e "${GREEN}[1/7]${NC} 检查环境..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}错误: Docker Compose 未安装${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker 环境检查通过"
echo ""

# 2. 构建API镜像
echo -e "${GREEN}[2/7]${NC} 构建API镜像..."
cd ../..
docker build -t knowhere-api:test -f deploy/docker/Dockerfile.api . 2>&1 | grep -E "(Step|Successfully|ERROR)" | tail -5
cd deploy/docker
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo -e "${RED}错误: 镜像构建失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} 镜像构建成功"
echo ""

# 3. 启动基础服务
echo -e "${GREEN}[3/7]${NC} 启动基础服务（PostgreSQL, Redis, RabbitMQ, MinIO, LocalStack）..."
docker-compose -f docker-compose.test.yml up -d postgres redis rabbitmq minio localstack

echo "等待服务就绪..."
sleep 10

# 检查服务健康状态
echo "检查服务状态..."
docker-compose -f docker-compose.test.yml ps

echo -e "${GREEN}✓${NC} 基础服务启动完成"
echo ""

# 4. 初始化MinIO存储桶
echo -e "${GREEN}[4/7]${NC} 初始化MinIO存储桶..."
sleep 5
docker exec knowhere-test-minio mc alias set local http://localhost:9000 minioadmin minioadmin123 2>/dev/null || true
docker exec knowhere-test-minio mc mb local/knowhere 2>/dev/null || echo "存储桶可能已存在"
docker exec knowhere-test-minio mc mb local/knowhere-uploads 2>/dev/null || echo "存储桶可能已存在"
docker exec knowhere-test-minio mc mb local/knowhere-results 2>/dev/null || echo "存储桶可能已存在"
echo -e "${GREEN}✓${NC} MinIO存储桶初始化完成"
echo ""

# 5. 启动API服务
echo -e "${GREEN}[5/7]${NC} 启动API服务..."
docker-compose -f docker-compose.test.yml up -d api

echo "等待API服务启动（最多120秒）..."
for i in {1..24}; do
    sleep 5
    if docker exec knowhere-test-api curl -f http://localhost:5005/health &>/dev/null; then
        echo -e "${GREEN}✓${NC} API服务健康检查通过"
        break
    fi
    echo "等待中... ($((i*5))秒)"
    if [ $i -eq 24 ]; then
        echo -e "${YELLOW}警告: API服务健康检查超时，查看日志:${NC}"
        docker logs knowhere-test-api --tail 50
        exit 1
    fi
done
echo ""

# 6. 运行测试
echo -e "${GREEN}[6/7]${NC} 运行API测试..."

# 测试健康检查端点
echo "测试健康检查端点..."
HEALTH_RESPONSE=$(curl -s http://localhost:5005/health)
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}✓${NC} 健康检查端点正常"
    echo "响应: $HEALTH_RESPONSE"
else
    echo -e "${RED}✗${NC} 健康检查端点异常"
    echo "响应: $HEALTH_RESPONSE"
fi
echo ""

# 测试根端点
echo "测试根端点..."
ROOT_RESPONSE=$(curl -s http://localhost:5005/)
if echo "$ROOT_RESPONSE" | grep -q "Welcome"; then
    echo -e "${GREEN}✓${NC} 根端点正常"
    echo "响应: $ROOT_RESPONSE"
else
    echo -e "${YELLOW}⚠${NC} 根端点响应异常"
    echo "响应: $ROOT_RESPONSE"
fi
echo ""

# 测试API文档
echo "测试API文档端点..."
if curl -s http://localhost:5005/docs | grep -q "swagger"; then
    echo -e "${GREEN}✓${NC} API文档可访问: http://localhost:5005/docs"
else
    echo -e "${YELLOW}⚠${NC} API文档可能不可用"
fi
echo ""

# 7. 显示服务信息
echo -e "${GREEN}[7/7]${NC} 服务信息汇总"
echo ""
echo -e "${BLUE}=== 服务访问地址 ===${NC}"
echo "  API服务:        http://localhost:5005"
echo "  API文档:        http://localhost:5005/docs"
echo "  API健康检查:    http://localhost:5005/health"
echo "  RabbitMQ管理:   http://localhost:15672 (admin/admin123)"
echo "  MinIO控制台:    http://localhost:9001 (minioadmin/minioadmin123)"
echo "  LocalStack:     http://localhost:4566"
echo ""
echo -e "${BLUE}=== 数据库连接信息 ===${NC}"
echo "  PostgreSQL:     localhost:5432"
echo "  数据库名:       Knowhere"
echo "  用户名:         root"
echo "  密码:           root123"
echo ""
echo -e "${BLUE}=== Redis连接信息 ===${NC}"
echo "  Redis:          localhost:6379"
echo "  密码:           (无)"
echo ""
echo -e "${BLUE}=== 查看日志 ===${NC}"
echo "  API日志:        docker logs -f knowhere-test-api"
echo "  所有服务日志:   docker-compose -f docker-compose.test.yml logs -f"
echo ""
echo -e "${BLUE}=== 停止服务 ===${NC}"
echo "  停止所有服务:   docker-compose -f docker-compose.test.yml down"
echo "  停止并清理:     docker-compose -f docker-compose.test.yml down -v"
echo ""

# 显示容器状态
echo -e "${BLUE}=== 容器状态 ===${NC}"
docker-compose -f docker-compose.test.yml ps

echo ""
echo -e "${GREEN}=== 部署测试完成 ===${NC}"
echo ""
echo -e "${YELLOW}提示:${NC} 使用 'docker logs -f knowhere-test-api' 查看API服务日志"

