# Docker完整部署测试指南

本指南介绍如何使用Docker Compose进行完整的API服务部署测试。

## 快速开始

### 1. 运行自动化测试脚本

```bash
cd deploy/docker
./test-deployment.sh
```

这个脚本会自动：
- 检查Docker环境
- 构建API镜像
- 启动所有依赖服务（PostgreSQL, Redis, RabbitMQ, MinIO, LocalStack）
- 初始化存储桶
- 启动API服务
- 运行健康检查测试
- 显示服务访问信息

### 2. 手动启动（分步操作）

```bash
cd deploy/docker

# 1. 构建API镜像
docker build -t knowhere-api:test -f Dockerfile.api ../..

# 2. 启动所有服务
docker-compose -f docker-compose.test.yml up -d

# 3. 查看服务状态
docker-compose -f docker-compose.test.yml ps

# 4. 查看API服务日志
docker logs -f knowhere-test-api

# 5. 测试健康检查
curl http://localhost:5005/health
```

## 服务配置

### 包含的服务

1. **PostgreSQL** (端口 5432)
   - 数据库: Knowhere
   - 用户: root
   - 密码: root123

2. **Redis** (端口 6379)
   - 无密码

3. **RabbitMQ** (端口 5672, 管理界面 15672)
   - 用户: admin
   - 密码: admin123

4. **MinIO** (API端口 9000, 控制台 9001)
   - 用户: minioadmin
   - 密码: minioadmin123
   - 存储桶: knowhere, knowhere-uploads, knowhere-results

5. **LocalStack** (端口 4566)
   - AWS服务模拟（S3, SNS等）

6. **API服务** (端口 5005)
   - 主服务
   - 健康检查: http://localhost:5005/health
   - API文档: http://localhost:5005/docs

## 环境变量配置

所有必要的环境变量已在 `docker-compose.test.yml` 中配置，包括：

- 数据库连接
- Redis配置
- RabbitMQ配置
- 存储配置（MinIO）
- AI模型配置（测试用）
- 路径配置
- 安全配置

### 使用自定义.env文件

如果需要使用自定义环境变量，可以：

1. 创建 `.env` 文件（基于 `apps/api/env.example`）
2. 修改 `docker-compose.test.yml` 中的环境变量部分
3. 或者使用 `env_file` 指令：

```yaml
api:
  env_file:
    - ../../.env
```

## 测试端点

### 健康检查
```bash
curl http://localhost:5005/health
```

### 根端点
```bash
curl http://localhost:5005/
```

### API文档
访问浏览器: http://localhost:5005/docs

## 查看日志

### 查看所有服务日志
```bash
docker-compose -f docker-compose.test.yml logs -f
```

### 查看特定服务日志
```bash
# API服务
docker logs -f knowhere-test-api

# PostgreSQL
docker logs -f knowhere-test-postgres

# Redis
docker logs -f knowhere-test-redis

# RabbitMQ
docker logs -f knowhere-test-rabbitmq

# MinIO
docker logs -f knowhere-test-minio
```

## 停止服务

### 停止所有服务（保留数据）
```bash
docker-compose -f docker-compose.test.yml down
```

### 停止并清理所有数据
```bash
docker-compose -f docker-compose.test.yml down -v
```

## 故障排查

### API服务无法启动

1. 检查依赖服务是否就绪：
```bash
docker-compose -f docker-compose.test.yml ps
```

2. 查看API服务日志：
```bash
docker logs knowhere-test-api
```

3. 检查环境变量：
```bash
docker exec knowhere-test-api env | grep -E "(DATABASE|REDIS|RABBITMQ|S3)"
```

### 数据库连接失败

1. 检查PostgreSQL是否运行：
```bash
docker exec knowhere-test-postgres pg_isready -U root
```

2. 测试连接：
```bash
docker exec knowhere-test-postgres psql -U root -d Knowhere -c "SELECT 1;"
```

### MinIO连接失败

1. 检查MinIO是否运行：
```bash
curl http://localhost:9000/minio/health/live
```

2. 访问控制台：http://localhost:9001

3. 检查存储桶：
```bash
docker exec knowhere-test-minio mc ls local/
```

## 性能测试

### 使用curl进行简单测试
```bash
# 健康检查
for i in {1..10}; do curl -s http://localhost:5005/health; echo; done

# 并发测试（需要安装apache bench）
ab -n 100 -c 10 http://localhost:5005/health
```

## 数据持久化

所有数据存储在Docker volumes中：
- `postgres_test_data`: PostgreSQL数据
- `redis_test_data`: Redis数据
- `rabbitmq_test_data`: RabbitMQ数据
- `minio_test_data`: MinIO数据
- `localstack_test_data`: LocalStack数据
- `api_test_users_data`: 用户数据
- `api_test_tmp_data`: 临时文件

清理所有数据：
```bash
docker-compose -f docker-compose.test.yml down -v
```

## 下一步

测试通过后，可以：
1. 使用生产环境的Docker Compose配置
2. 部署到AWS ECS Fargate
3. 部署到阿里云ACK
4. 参考 `deploy/README.md` 了解生产部署方案

