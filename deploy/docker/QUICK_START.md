# 快速开始 - 完整部署测试

## 一键启动

```bash
cd deploy/docker
./test-deployment.sh
```

## 手动启动

```bash
cd deploy/docker

# 1. 构建镜像
docker build -t knowhere-api:test -f Dockerfile.api ../..

# 2. 启动所有服务
docker-compose -f docker-compose.test.yml up -d

# 3. 查看日志
docker logs -f knowhere-test-api

# 4. 测试
curl http://localhost:5005/health
```

## 服务访问

- **API服务**: http://localhost:5005
- **API文档**: http://localhost:5005/docs
- **RabbitMQ管理**: http://localhost:15672 (admin/admin123)
- **MinIO控制台**: http://localhost:9001 (minioadmin/minioadmin123)

## 停止服务

```bash
docker-compose -f docker-compose.test.yml down
```

## 清理所有数据

```bash
docker-compose -f docker-compose.test.yml down -v
```

详细文档请参考 [README_TEST.md](README_TEST.md)

