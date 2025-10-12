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

### 安装依赖

```bash
pnpm install
```

### 开发模式

```bash
# 启动所有服务
pnpm dev

# 或单独启动
pnpm dev:api       # 后端 API
pnpm dev:web       # 前端应用
pnpm dev:docs      # 文档站
pnpm dev:worker    # 异步任务 Worker
pnpm dev:flower    # Celery 监控界面
```

### 异步任务系统

项目使用 Celery 作为异步任务队列，支持以下功能：

- **文档处理**: 智能解析和向量化文档
- **知识库编码**: 批量处理知识库数据
- **表格填充**: 智能表格数据填充
- **AI 查询**: 异步 AI 服务调用

#### 启动异步 Worker

```bash
# 1. 启动依赖服务（RabbitMQ、Redis、MySQL）
pnpm dev:services

# 2. 启动异步 Worker
pnpm dev:worker

# 3. 启动 Flower 监控（可选）
pnpm dev:flower
```

#### 监控任务状态

- **Flower 监控**: http://localhost:5555
- **RabbitMQ 管理**: http://localhost:15672 (admin/admin123)

### 类型生成

```bash
# 导出 FastAPI OpenAPI schema 并生成类型
pnpm generate:types
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
