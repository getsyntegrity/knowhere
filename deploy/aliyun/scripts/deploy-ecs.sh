#!/bin/bash
set -e

SERVICE_NAME="$1"
IMAGE_FULL="$2"
COMPOSE_DIR="/var/lib/knowhere"
COMPOSE_FILE="docker-compose.ecs.yaml"

echo "🔧 开始部署 $SERVICE_NAME 服务"
echo "📁 工作目录: $COMPOSE_DIR"
echo "🐳 目标镜像: $IMAGE_FULL"

# 切换到工作目录
cd "$COMPOSE_DIR" || { echo "❌ 无法进入目录: $COMPOSE_DIR"; exit 1; }

# 检查 Docker Compose 文件
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ Docker Compose 文件不存在: $COMPOSE_FILE"
  exit 1
fi

echo "📋 当前Docker Compose状态:"
docker-compose -f "$COMPOSE_FILE" ps

# 拉取新镜像
echo "⬇️ 拉取新镜像..."
docker pull "$IMAGE_FULL" || { 
  echo "❌ 拉取镜像失败"
  exit 1
}

# 更新 Docker Compose 文件中的镜像标签
echo "📝 更新 Docker Compose 配置..."
BACKUP_FILE="$COMPOSE_FILE.backup.$(date +%Y%m%d%H%M%S)"
cp "$COMPOSE_FILE" "$BACKUP_FILE"
echo "📄 已备份原文件到: $BACKUP_FILE"

if [ "$SERVICE_NAME" = "api" ]; then
  sed -i "s|image:.*knowhere-registry.cn-shenzhen.cr.aliyuncs.com/knowhere/knowhere-backend:.*|image: $IMAGE_FULL|" "$COMPOSE_FILE"
  echo "✅ 已更新API服务镜像"
elif [ "$SERVICE_NAME" = "web" ]; then
  sed -i "s|image:.*knowhere-registry.cn-shenzhen.cr.aliyuncs.com/knowhere/knowhere-frontend:.*|image: $IMAGE_FULL|" "$COMPOSE_FILE"
  echo "✅ 已更新Web服务镜像"
elif [ "$SERVICE_NAME" = "worker" ]; then
  sed -i "s|image:.*knowhere-registry.cn-shenzhen.cr.aliyuncs.com/knowhere/knowhere-worker:.*|image: $IMAGE_FULL|" "$COMPOSE_FILE"
  echo "✅ 已更新Worker服务镜像"
else
  echo "❌ 未知服务名: $SERVICE_NAME"
  exit 1
fi

# 重启服务
echo "🔄 重启服务 $SERVICE_NAME..."
docker-compose -f "$COMPOSE_FILE" up -d "$SERVICE_NAME"

# 等待并检查服务状态
echo "⏳ 等待服务启动(15秒)..."
sleep 15

echo "🔍 检查服务状态:"
docker-compose -f "$COMPOSE_FILE" ps "$SERVICE_NAME"

# 检查容器状态
CONTAINER_ID=$(docker-compose -f "$COMPOSE_FILE" ps -q "$SERVICE_NAME")
if [ -n "$CONTAINER_ID" ]; then
  CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER_ID" 2>/dev/null || echo "unknown")
  if [ "$CONTAINER_STATUS" = "running" ]; then
    echo "✅ 服务 $SERVICE_NAME 已成功启动!"
    echo "📄 最近日志:"
    docker-compose -f "$COMPOSE_FILE" logs --tail=10 "$SERVICE_NAME" 2>/dev/null || echo "无法获取日志"
  else
    echo "❌ 服务 $SERVICE_NAME 未正常运行"
    exit 1
  fi
else
  echo "❌ 未找到 $SERVICE_NAME 的容器"
  exit 1
fi

echo "🎉 $SERVICE_NAME 部署完成!"
