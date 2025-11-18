# 本地开发环境

本目录包含用于本地开发的基础设施服务配置。

## 服务说明

### 包含的服务

- **RabbitMQ**: 消息队列服务
  - 端口: 5672 (AMQP), 15672 (管理界面)
  - 用户名/密码: admin/admin123

- **Redis**: 缓存服务
  - 端口: 6379
  - 无密码

- **PostgreSQL**: 数据库服务
  - 端口: 5432
  - 用户: root/root123
  - 数据库: Knowhere

- **MinIO**: 对象存储服务
  - 端口: 9000 (API), 9001 (控制台)
  - 用户名/密码: minioadmin/minioadmin123

## 快速开始

### 1. 启动服务

```bash
# 使用启动脚本（推荐）
./scripts/start_local_dev.sh

# 或手动启动
cd deploy
docker-compose -f docker-compose.queue.yml up -d
```

### 2. 配置环境变量

```bash
# 复制环境配置模板
cp env.local.example .env

# 编辑配置文件
vim .env
```

### 3. 停止服务

```bash
# 使用停止脚本
./scripts/stop_local_dev.sh

# 或手动停止
cd deploy
docker-compose -f docker-compose.queue.yml down
```

## 服务访问

| 服务 | 地址 | 用户名/密码 |
|------|------|-------------|
| RabbitMQ 管理界面 | http://localhost:15672 | admin/admin123 |
| MinIO 控制台 | http://localhost:9001 | minioadmin/minioadmin123 |
| PostgreSQL | localhost:5432 | root/root123 |
| Redis | localhost:6379 | 无密码 |

## 数据持久化

所有数据都通过 Docker volumes 持久化存储：

- `rabbitmq_data`: RabbitMQ 数据
- `redis_data`: Redis 数据
- `postgres_data`: PostgreSQL 数据
- `minio_data`: MinIO 数据

## 清理数据

如需完全清理所有数据：

```bash
cd deploy
docker-compose -f docker-compose.queue.yml down -v
```

## 故障排除

### 检查服务状态

```bash
cd deploy
docker-compose -f docker-compose.queue.yml ps
```

### 查看服务日志

```bash
cd deploy
docker-compose -f docker-compose.queue.yml logs [service_name]
```

### 重启特定服务

```bash
cd deploy
docker-compose -f docker-compose.queue.yml restart [service_name]
```
