# Knowhere Monorepo

基于 pnpm workspace + Turborepo 的 monorepo 架构，包含前端、后端、文档站和 SDK 项目。

## 项目结构

```
knowhere/
├── apps/                        # 应用层
│   ├── web/                     # Next.js 前端应用
│   ├── api/                     # FastAPI 后端应用
│   └── docs/                    # 文档站
├── packages/                    # 共享包和 SDK
│   ├── sdk-typescript/          # TypeScript SDK
│   ├── sdk-python/              # Python SDK
│   ├── shared-types/            # 共享类型定义
│   └── openapi-specs/           # OpenAPI 规范和生成脚本
```

## 快速开始

### 环境要求

- Node.js 18+ 和 pnpm
- Python 3.9+ 和 pip
- Docker 和 Docker Compose
- Git

### 安装依赖

```bash
# 安装根目录依赖
pnpm install

# 安装 Python 依赖
cd apps/api
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 开发环境启动

#### 方式一：一键启动（推荐）

```bash
# 1. 启动所有依赖服务（MySQL、Redis、RabbitMQ、MinIO）或 根目录执行 pnpm dev:services
cd apps/api/deploy
./start-dev.sh

# 2. 启动后端 API 服务
cd ../../../
pnpm dev:api

# 3. 启动异步任务 Worker（新终端）
pnpm dev:worker

# 3. 启动前端应用（新终端）
pnpm dev:web

# 4. 启动文档站（可选，新终端）
pnpm dev:docs
```

#### 方式二：分步启动

```bash
# 1. 启动基础服务
pnpm dev:services

# 2. 启动后端 API
pnpm dev:api

# 3. 启动前端应用
pnpm dev:web

# 4. 启动异步任务 Worker（可选）
pnpm dev:worker

# 5. 启动 Flower 监控（可选）
pnpm dev:flower
```

### 服务访问地址

启动完成后，可通过以下地址访问各服务：

- **前端应用**: http://localhost:3000
- **后端 API**: http://localhost:5005
- **API 文档**: http://localhost:5005/docs
- **文档站**: http://localhost:3001
- **MinIO 控制台**: http://localhost:9001 (minioadmin/minioadmin123)
- **MySQL**: localhost:3306 (aismart_user/aismart123)
- **Redis**: localhost:6379
- **RabbitMQ 管理**: http://localhost:15672 (admin/admin123)
- **Flower 监控**: http://localhost:5555

### 异步任务系统

项目使用 Celery 作为异步任务队列，支持以下功能：

- **文档处理**: 智能解析和向量化文档
- **知识库编码**: 批量处理知识库数据
- **表格填充**: 智能表格数据填充
- **AI 查询**: 异步 AI 服务调用

#### 启动异步 Worker

```bash
# 1. 确保依赖服务已启动
pnpm dev:services

# 2. 启动异步 Worker
pnpm dev:worker

# 3. 启动 Flower 监控（可选）
pnpm dev:flower
```

#### 监控任务状态

- **Flower 监控**: http://localhost:5555
- **RabbitMQ 管理**: http://localhost:15672 (admin/admin123)

### 测试环境

```bash
# 测试 S3 webhook
curl -X POST http://localhost:5005/v1/internal/s3-events \
  -H 'Content-Type: application/json' \
  -H 'x-minio-auth-token: dev-webhook-token' \
  -d '{"Records":[{"eventName":"s3:ObjectCreated:Put","s3":{"bucket":{"name":"knowhere-uploads"},"object":{"key":"uploads/job_test123.pdf"}}}]}'
```

### 停止服务

```bash
# 停止所有 Docker 服务
cd apps/api/deploy
docker-compose -f docker-compose.dev.yml down

# 或使用 pnpm 命令
pnpm dev:services --down
```

### 类型生成

```bash
# 导出 FastAPI OpenAPI schema 并生成类型
pnpm generate:types
```

## 部署指南

### 生产环境部署

#### 1. 环境准备

```bash
# 克隆代码
git clone <repository-url>
cd knowhere

# 安装依赖
pnpm install
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. 环境配置

```bash
# 复制环境变量模板
cd apps/api
cp env.example .env

# 编辑环境变量
vim .env
```

主要配置项：
- `DATABASE_URL`: MySQL 数据库连接
- `REDIS_URL`: Redis 连接
- `RABBITMQ_URL`: RabbitMQ 连接
- `MINIO_ENDPOINT`: MinIO 服务地址
- `MINIO_ACCESS_KEY`: MinIO 访问密钥
- `MINIO_SECRET_KEY`: MinIO 秘密密钥
- `JWT_SECRET_KEY`: JWT 签名密钥

#### 3. 数据库初始化

```bash
# 创建数据库表
cd apps/api
source venv/bin/activate
python -c "from app.core.database import engine; from app.models import Base; Base.metadata.create_all(bind=engine)"
```

#### 4. 启动服务

```bash
# 启动 API 服务
cd apps/api
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# 启动异步 Worker
python worker.py

# 启动前端（生产构建）
cd apps/web
pnpm build
pnpm start
```

#### 5. 使用 Docker 部署

```bash
# 构建镜像
cd apps/api
docker build -t knowhere-api .

# 运行容器
docker run -d \
  --name knowhere-api \
  -p 8000:8000 \
  --env-file .env \
  knowhere-api
```

### 开发环境部署

#### 使用 Docker Compose

```bash
# 启动所有服务
cd apps/api/deploy
docker-compose -f docker-compose.dev.yml up -d

# 查看服务状态
docker-compose -f docker-compose.dev.yml ps

# 查看日志
docker-compose -f docker-compose.dev.yml logs -f

# 停止服务
docker-compose -f docker-compose.dev.yml down
```

#### 服务管理

```bash
# 重启特定服务
docker-compose -f docker-compose.dev.yml restart mysql

# 查看服务日志
docker-compose -f docker-compose.dev.yml logs mysql

# 进入容器
docker exec -it knowhere_mysql bash
```

### 监控和维护

#### 健康检查

```bash
# 检查 API 健康状态
curl http://localhost:5005/health

# 检查数据库连接
docker exec knowhere_mysql mysqladmin ping -h localhost -u root -proot123

# 检查 Redis 连接
docker exec knowhere_redis redis-cli ping

# 检查 MinIO 状态
curl http://localhost:9000/minio/health/live
```

#### 日志管理

```bash
# 查看应用日志
tail -f apps/api/logs/app_$(date +%Y-%m-%d).log

# 查看 Docker 服务日志
docker-compose -f docker-compose.dev.yml logs -f --tail=100
```

#### 数据备份

```bash
# 备份 MySQL 数据
docker exec knowhere_mysql mysqldump -u root -proot123 aismart_bid > backup_$(date +%Y%m%d).sql

# 备份 Redis 数据
docker exec knowhere_redis redis-cli --rdb /data/dump.rdb
```

### 故障排除

#### 常见问题

**1. Docker 服务启动失败**
```bash
# 检查 Docker 状态
docker info

# 重启 Docker 服务
sudo systemctl restart docker  # Linux
# 或重启 Docker Desktop (Mac/Windows)
```

**2. 端口冲突**
```bash
# 检查端口占用
lsof -i :3306  # MySQL
lsof -i :6379  # Redis
lsof -i :5672  # RabbitMQ
lsof -i :9000  # MinIO

# 停止占用进程
sudo kill -9 <PID>
```

**3. 数据库连接失败**
```bash
# 检查 MySQL 容器状态
docker exec knowhere_mysql mysqladmin ping -h localhost -u root -proot123

# 查看 MySQL 日志
docker logs knowhere_mysql

# 重启 MySQL 容器
docker restart knowhere_mysql
```

**4. Python 环境问题**
```bash
# 重新创建虚拟环境
cd apps/api
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**5. 权限问题**
```bash
# 给启动脚本执行权限
chmod +x apps/api/deploy/start-dev.sh

# 修复 Docker 权限（Linux）
sudo usermod -aG docker $USER
# 然后重新登录
```

#### 清理环境

```bash
# 停止所有服务
cd apps/api/deploy
docker-compose -f docker-compose.dev.yml down

# 清理 Docker 资源
docker system prune -a

# 清理数据卷（注意：会删除所有数据）
docker-compose -f docker-compose.dev.yml down -v

# 重新启动
./start-dev.sh
```

## 技术栈

- **前端**: Next.js 14+ + TypeScript + Tailwind CSS + Shadcn UI
- **后端**: FastAPI + Pydantic + SQLAlchemy + Redis
- **异步任务**: Celery + RabbitMQ + Flower
- **数据库**: MySQL + Redis
- **SDK**: TypeScript SDK + Python SDK
- **构建工具**: pnpm workspace + Turborepo
- **类型同步**: OpenAPI + openapi-typescript

## 开发工作流程

1. 后端开发者更新 API 代码
2. 运行 `pnpm api:export-schema` 导出 OpenAPI schema
3. 运行 `pnpm generate:types` 自动生成前后端类型
4. 前端、文档站和 SDK 自动获得最新的类型定义
