# Worker部署解决方案

## 问题分析

你的分析完全正确！当前项目存在以下问题：

### 🚨 当前问题
1. **项目有独立的Worker**: `worker.py`文件是Celery Worker进程
2. **Dockerfile只启动API**: 当前Dockerfile只启动`main.py`（FastAPI服务）
3. **Worker未启动**: 在ECS Fargate环境中，Worker服务没有运行
4. **任务无法处理**: Celery任务会堆积在队列中，无法被处理

### 📊 影响范围
- 异步任务无法执行（文档处理、AI查询等）
- 任务队列会不断堆积
- 系统功能不完整

## 解决方案

我提供了两种解决方案，推荐使用**方案一**：

### 方案一：独立Worker容器（推荐）

#### 优势
- ✅ 服务隔离，故障独立
- ✅ 独立扩缩容
- ✅ 资源使用优化
- ✅ 易于监控和调试

#### 架构
```
┌─────────────────┬─────────────────┬─────────────────┐
│   Frontend      │   Backend       │   Worker        │
│   (Next.js)     │   (FastAPI)     │   (Celery)      │
│   ECS Fargate   │   ECS Fargate   │   ECS Fargate   │
└─────────────────┴─────────────────┴─────────────────┘
    ↓                     ↓                     ↓
    └─────────┬───────────┴─────────────────────┘
              ↓
    ┌─────────────────────────┐
    │   RDS + Redis + S3      │
    └─────────────────────────┘
```

#### 文件结构
```
deploy/aws/
├── ecs-task-definition-worker.json    # Worker任务定义
├── ecs-service-worker.json           # Worker服务配置
└── scripts/
    ├── build-and-push.sh             # 构建脚本（已更新）
    └── deploy.sh                     # 部署脚本（已更新）

apps/api/
├── Dockerfile                        # API服务镜像
├── Dockerfile.worker                 # Worker专用镜像
└── worker.py                         # Worker启动脚本
```

### 方案二：Supervisor管理多进程

#### 优势
- ✅ 单容器部署
- ✅ 资源使用更少
- ✅ 配置简单

#### 劣势
- ❌ 进程耦合，故障影响大
- ❌ 扩缩容不灵活
- ❌ 调试困难

## 部署步骤

### 1. 使用方案一（推荐）

```bash
# 1. 构建和推送所有镜像
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
./deploy/aws/scripts/build-and-push.sh

# 2. 部署基础设施
cd deploy/aws/terraform
terraform init
terraform plan
terraform apply

# 3. 部署ECS服务
./deploy/aws/scripts/deploy.sh all
```

### 2. 使用方案二（Supervisor）

```bash
# 修改Dockerfile为使用Supervisor版本
cp apps/api/Dockerfile.supervisor apps/api/Dockerfile

# 然后正常部署
./deploy/aws/scripts/build-and-push.sh
./deploy/aws/scripts/deploy.sh all
```

## 验证部署

### 检查服务状态
```bash
# 检查ECS服务
aws ecs describe-services \
  --cluster knowhere-cluster \
  --services knowhere-backend-service knowhere-frontend-service knowhere-worker-service

# 检查任务状态
aws ecs list-tasks --cluster knowhere-cluster
```

### 检查Worker日志
```bash
# 查看Worker日志
aws logs get-log-events \
  --log-group-name /ecs/knowhere-worker \
  --log-stream-name <stream-name>
```

### 测试Celery任务
```bash
# 进入API容器
aws ecs execute-command \
  --cluster knowhere-cluster \
  --task <task-arn> \
  --container knowhere-backend \
  --interactive \
  --command "/bin/bash"

# 在容器中测试
python -c "
from app.core.celery_app import celery_app
result = celery_app.send_task('app.core.tasks.celery_tasks.test_task')
print(f'Task ID: {result.id}')
"
```

## 监控和调试

### CloudWatch日志
- **API服务**: `/ecs/knowhere-backend`
- **前端服务**: `/ecs/knowhere-frontend`
- **Worker服务**: `/ecs/knowhere-worker`

### 健康检查
- **API服务**: `https://api.yourdomain.com/health`
- **前端服务**: `https://yourdomain.com/`
- **Worker服务**: Celery stats检查

### 常见问题排查

#### 1. Worker无法启动
```bash
# 检查环境变量
aws ecs describe-task-definition --task-definition knowhere-worker

# 检查日志
aws logs get-log-events --log-group-name /ecs/knowhere-worker
```

#### 2. 任务无法执行
```bash
# 检查Celery连接
python -c "from app.core.celery_app import celery_app; print(celery_app.control.inspect().stats())"

# 检查队列状态
python -c "from app.core.celery_app import celery_app; print(celery_app.control.inspect().active_queues())"
```

#### 3. 数据库连接问题
```bash
# 检查数据库连接
python -c "from app.core.database import engine; print(engine.url)"
```

## 成本优化

### 资源建议
- **API服务**: 1 vCPU, 2GB RAM
- **前端服务**: 0.5 vCPU, 1GB RAM  
- **Worker服务**: 1 vCPU, 2GB RAM（可根据任务负载调整）

### 自动扩缩容
```bash
# 配置Worker自动扩缩容
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/knowhere-cluster/knowhere-worker-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 5
```

## 总结

通过以上解决方案，你的项目将能够：

1. ✅ **完整运行**: API服务 + Worker服务同时运行
2. ✅ **任务处理**: 异步任务能够正常执行
3. ✅ **独立扩缩容**: 各服务可以独立调整资源
4. ✅ **监控完整**: 所有服务都有独立的日志和监控
5. ✅ **故障隔离**: 单个服务故障不影响其他服务

推荐使用**方案一**（独立Worker容器），这样能够获得更好的可维护性和扩展性。
